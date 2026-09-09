"""Periodic tasks to reconcile local boleto status with Sicredi.

Two complementary jobs cover the "client paid but the platform never updated"
gap when a webhook is missed:

* ``sync_open_boletos`` (hourly): re-queries each open boleto individually and
  applies the reported situação. Cheap safety net.
* ``reconcile_liquidados`` (daily, early morning): pulls Sicredi's batch list of
  boletos liquidated yesterday and today and marks the local records paid —
  authoritative catch-all that does not depend on the local status being open.

Both write an OUTBOUND audit event per run so admins can SEE in the frontend
that reconciliation is actually running (which also proves beat+worker are up).
"""

import asyncio

from app.tasks._async_helpers import TaskSessionFactory, run_in_task_loop
from app.tasks.celery_app import celery
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Sicredi situacao -> local BoletoStatus value (resolved lazily inside the task).
_SITUACAO_MAP = {
    "LIQUIDADO": "LIQUIDADO",
    "BAIXADO": "CANCELADO",
    "BAIXADO POR SOLICITACAO": "CANCELADO",
    "VENCIDO": "VENCIDO",
    "NEGATIVADO": "NEGATIVADO",
    "NORMAL": "NORMAL",
}

# Situações that just mean "still open at Sicredi". The consulta returns
# "EM CARTEIRA" for every registered, unpaid boleto, so without this every
# healthy boleto was reported back as an unmapped situação and the run looked
# broken. They are a deliberate no-op: whether the title is merely open or
# already past due is decided locally, not by this label.
_SITUACAO_OPEN = frozenset({
    "EM CARTEIRA",
    "EM ABERTO",
    "ABERTO",
    "A VENCER",
    "REGISTRADO",
})


def resolve_situacao(situacao: str) -> tuple[str | None, bool]:
    """Map a Sicredi situação to a local status value.

    Returns ``(status_value, known)``. ``status_value`` is None when nothing
    should change; ``known`` is False only for labels we have never seen, which
    are the ones worth surfacing to an admin.
    """
    normalized = " ".join((situacao or "").strip().upper().split())
    if not normalized:
        return None, True
    if normalized in _SITUACAO_OPEN:
        return None, True
    mapped = _SITUACAO_MAP.get(normalized)
    if mapped:
        return mapped, True
    # Sicredi appends the settlement channel to the label. The webhook contract
    # covers liquidações via Pix, Canais Sicredi (Rede), Outras Instituições
    # (COMPE) and Cartório, and the consulta echoes those back as "LIQUIDADO
    # COMPE", "LIQUIDADO CARTORIO" and so on. The docs give the situação list as
    # an example, not an enumeration, so match the family: every member of it
    # means the money arrived, whichever bank collected it.
    if normalized.startswith("LIQUIDADO") and "PARCIAL" not in normalized:
        return "LIQUIDADO", True
    # BAIXADO is deliberately NOT matched by prefix. Cancelling a title stops
    # the charge, so an unfamiliar write-off label must reach an admin instead
    # of being guessed at.
    return None, False


# Sicredi spells the settlement date and amount differently per endpoint, and
# ConsultaBoletoResponse keeps unknown fields (extra="allow"), so probe every
# spelling seen — the same set reconcile_liquidados already reads.
_DATA_LIQ_KEYS = ("dataLiquidacao", "dataPagamento", "dataEvento")
_VALOR_LIQ_KEYS = ("valorLiquidacao", "valorPago")


def extract_liquidacao(data):
    """Return ``(valor, data_liquidacao)`` carried by a consulta response.

    A payment made through another bank is only noticed on the next run, so
    without this the boleto is recorded as settled *today* with no amount —
    wrong in every report that groups receipts by payment date.
    """
    from decimal import Decimal, InvalidOperation

    from app.services.boleto_status_service import parse_sicredi_date

    payload = data.model_dump() if hasattr(data, "model_dump") else dict(data or {})

    valor = None
    for key in _VALOR_LIQ_KEYS:
        raw = payload.get(key)
        if raw in (None, ""):
            continue
        try:
            valor = Decimal(str(raw))
        except (InvalidOperation, ValueError):
            logger.warning("sicredi_valor_liquidacao_unparseable", value=str(raw)[:40])
        break

    data_liq = None
    for key in _DATA_LIQ_KEYS:
        raw = payload.get(key)
        if not raw:
            continue
        data_liq = parse_sicredi_date(str(raw))
        if data_liq:
            break

    return valor, data_liq


# Max boletos reconciled per company per run, to bound Sicredi API usage.
_MAX_PER_COMPANY = 200


async def sync_company_open_boletos(db, sicredi_client, company_id, *, delay: float = 0.35) -> dict:
    """Reconcile one company's open boletos with Sicredi and return a summary.

    Shared by the hourly Celery task and the on-demand admin "sync-all" endpoint.
    Writes one SYNC_RUN audit event (with error_samples so a full-run failure's
    cause is visible) and returns the same counts to the caller. The caller
    commits and persists the token cache.
    """
    from sqlalchemy import select

    from app.models.boleto import Boleto
    from app.models.enums import BoletoStatus, WriteoffType
    from app.services.boleto_status_service import mark_boleto_liquidado
    from app.services.sicredi.exceptions import SicrediError
    from app.services.sicredi_audit_service import DIRECTION_OUTBOUND, log_sicredi_event

    open_boletos = (await db.execute(
        select(Boleto)
        .where(
            Boleto.company_id == company_id,
            Boleto.status.in_([BoletoStatus.NORMAL, BoletoStatus.VENCIDO]),
            Boleto.nosso_numero.isnot(None),
        )
        # Oldest due date first: when the cap trims the run, the boletos most
        # likely to have been paid are the ones that get checked.
        .order_by(Boleto.data_vencimento.asc())
        .limit(_MAX_PER_COMPANY)
    )).scalars().all()

    updated = 0
    consult_errors = 0
    write_errors = 0
    unknown_situacoes: set = set()
    error_samples: dict = {}  # error message -> first nosso_numero that hit it

    for idx, boleto in enumerate(open_boletos):
        # Space out calls so Sicredi doesn't rate-limit the whole run.
        if idx > 0 and delay > 0:
            await asyncio.sleep(delay)
        try:
            data = await sicredi_client.boletos.consultar_por_nosso_numero(
                boleto.nosso_numero
            )
        except Exception as exc:
            # Anything that isn't a SicrediError (a parsing slip, a dropped
            # connection) used to abort the whole run and leave no SYNC_RUN
            # behind, so the admin saw nothing at all. Count it and move on.
            consult_errors += 1
            detail = str(getattr(exc, "detail", None) or exc) or exc.__class__.__name__
            status_code = getattr(exc, "status_code", None)
            if not isinstance(exc, SicrediError):
                detail = f"{exc.__class__.__name__}: {detail}"
            key = f"HTTP {status_code}: {detail}" if status_code else detail
            if key not in error_samples and len(error_samples) < 5:
                error_samples[key] = boleto.nosso_numero
            logger.warning(
                "sicredi_sync_consult_failed",
                nosso_numero=boleto.nosso_numero,
                status_code=status_code,
                error=detail,
            )
            continue

        situacao = (data.situacao or "").strip().upper()
        mapped, known = resolve_situacao(situacao)
        if not mapped:
            if not known:
                unknown_situacoes.add(situacao)
            continue
        new_status = BoletoStatus(mapped)
        if new_status == boleto.status:
            continue

        # Savepoint per boleto: one row the database refuses (a constraint, an
        # enum value the type doesn't have yet) used to poison the session and
        # take down the whole run, including the SYNC_RUN row that would have
        # explained it.
        try:
            async with db.begin_nested():
                if new_status == BoletoStatus.LIQUIDADO:
                    valor_liq, data_liq = extract_liquidacao(data)
                    await mark_boleto_liquidado(
                        db,
                        boleto,
                        valor=valor_liq,
                        data_liquidacao=data_liq,
                        source="sync_open_boletos",
                    )
                else:
                    boleto.status = new_status
                    if situacao in ("BAIXADO", "BAIXADO POR SOLICITACAO"):
                        if boleto.writeoff_type != WriteoffType.MANUAL_ADMIN:
                            boleto.writeoff_type = WriteoffType.BAIXA_EXTERNA
                            boleto.writeoff_reason = (
                                f"Baixa externa via Sicredi (situacao: {data.situacao}). "
                                "Sincronizado por tarefa periódica."
                            )
                    await db.flush()
        except Exception as exc:
            write_errors += 1
            nosso_numero = boleto.nosso_numero
            # Detach the rejected boleto so the commit at the end of the run
            # doesn't replay the same failing UPDATE.
            db.expunge(boleto)
            key = f"Falha ao gravar {new_status.value}: {exc.__class__.__name__}: {exc}"
            if key not in error_samples and len(error_samples) < 5:
                error_samples[key] = nosso_numero
            logger.warning(
                "sicredi_sync_write_failed",
                nosso_numero=nosso_numero,
                new_status=new_status.value,
                error=str(exc),
            )
            continue
        updated += 1

    summary = {
        "checked": len(open_boletos),
        "updated": updated,
        "consult_errors": consult_errors,
        "write_errors": write_errors,
        "unknown_situacoes": sorted(unknown_situacoes),
        # Distinct error messages (with an example boleto) so the cause of a
        # full-run failure is visible on the audit page and in the sync dialog.
        "error_samples": [
            {"error": k, "nosso_numero": v} for k, v in error_samples.items()
        ],
    }

    # Heartbeat: proves the job ran for this company and how much it did.
    await log_sicredi_event(
        db,
        direction=DIRECTION_OUTBOUND,
        event_type="SYNC_RUN",
        company_id=company_id,
        success=True,
        payload=summary,
    )
    return summary


async def _log_sync_failure(db, company_id, message: str) -> None:
    """Record a failed SYNC_RUN so the admin UI shows why nothing happened."""
    from app.services.sicredi_audit_service import DIRECTION_OUTBOUND, log_sicredi_event

    try:
        await log_sicredi_event(
            db,
            direction=DIRECTION_OUTBOUND,
            event_type="SYNC_RUN",
            company_id=company_id,
            success=False,
            payload={
                "checked": 0,
                "updated": 0,
                "consult_errors": 0,
                "write_errors": 0,
                "unknown_situacoes": [],
                "error_samples": [{"error": message, "nosso_numero": ""}],
            },
        )
        await db.commit()
    except Exception:  # auditing must never mask the original failure
        logger.warning("sicredi_sync_failure_audit_failed", company_id=str(company_id))
        await db.rollback()


async def _sync_open_boletos_async(session_factory: TaskSessionFactory):
    from sqlalchemy import select

    from app.models.sicredi_credential import SicrediCredential
    from app.services import sicredi_service

    async with session_factory() as db:
        company_ids = (await db.execute(
            select(SicrediCredential.company_id).distinct()
        )).scalars().all()

        total_synced = 0
        for cid in company_ids:
            try:
                sicredi_client = await sicredi_service.get_sicredi_client(db, cid)
            except Exception as exc:
                logger.warning("sicredi_sync_no_client", company_id=str(cid), error=str(exc))
                await db.rollback()
                await _log_sync_failure(
                    db, cid, f"Falha ao carregar credencial Sicredi: {exc}"
                )
                continue

            try:
                summary = await sync_company_open_boletos(db, sicredi_client, cid)
                total_synced += summary["updated"]
                await sicredi_service.persist_token_cache(db, cid)
                await db.commit()
            except Exception as exc:
                # One tenant's failure must not take the whole scheduled run down.
                logger.exception("sicredi_sync_company_failed", company_id=str(cid))
                await db.rollback()
                await _log_sync_failure(db, cid, f"Falha na sincronização: {exc}")

        logger.info("sicredi_sync_completed", total_synced=total_synced)


async def _reconcile_liquidados_async(session_factory: TaskSessionFactory):
    from sqlalchemy import select

    from app.models.boleto import Boleto
    from app.models.enums import BoletoStatus
    from app.models.sicredi_credential import SicrediCredential
    from app.services import sicredi_service
    from app.services.boleto_status_service import (
        mark_boleto_liquidado,
        parse_sicredi_date,
        today_brazil,
    )
    from app.services.sicredi.exceptions import SicrediError
    from app.services.sicredi_audit_service import DIRECTION_OUTBOUND, log_sicredi_event

    from datetime import timedelta

    today = today_brazil()
    dias = [today - timedelta(days=1), today]

    async with session_factory() as db:
        company_ids = (await db.execute(
            select(SicrediCredential.company_id).distinct()
        )).scalars().all()

        total_updated = 0
        for cid in company_ids:
            try:
                sicredi_client = await sicredi_service.get_sicredi_client(db, cid)
            except Exception as exc:
                logger.warning("sicredi_reconcile_no_client", company_id=str(cid), error=str(exc))
                continue

            for dia in dias:
                dia_str = dia.strftime("%d/%m/%Y")
                try:
                    liquidados = await sicredi_client.boletos.consultar_liquidados_dia(dia_str)
                except SicrediError as exc:
                    logger.warning(
                        "sicredi_reconcile_consult_failed",
                        company_id=str(cid),
                        dia=dia_str,
                        error=str(exc.detail or exc),
                    )
                    await log_sicredi_event(
                        db,
                        direction=DIRECTION_OUTBOUND,
                        event_type="SYNC_LIQUIDADOS_DIA",
                        company_id=cid,
                        success=False,
                        payload={"dia": dia_str, "error": str(exc.detail or exc)},
                    )
                    await db.commit()
                    continue

                returned = len(liquidados) if isinstance(liquidados, list) else 0
                updated = 0
                already = 0
                unmatched: list[str] = []

                for item in liquidados if isinstance(liquidados, list) else []:
                    if not isinstance(item, dict):
                        continue
                    nn = item.get("nossoNumero") or item.get("nosso_numero")
                    if not nn:
                        continue
                    boleto = (await db.execute(
                        select(Boleto).where(
                            Boleto.nosso_numero == str(nn),
                            Boleto.company_id == cid,
                        )
                    )).scalar_one_or_none()
                    if not boleto:
                        unmatched.append(str(nn))
                        continue
                    if boleto.status == BoletoStatus.LIQUIDADO:
                        already += 1
                        continue
                    data_liq = (
                        parse_sicredi_date(
                            item.get("dataLiquidacao")
                            or item.get("dataEvento")
                            or item.get("dataPagamento")
                        )
                        or dia
                    )
                    valor = item.get("valorLiquidacao") or item.get("valorPago")
                    await mark_boleto_liquidado(
                        db, boleto, valor=valor, data_liquidacao=data_liq, source="reconcile_liquidados"
                    )
                    updated += 1

                total_updated += updated
                await log_sicredi_event(
                    db,
                    direction=DIRECTION_OUTBOUND,
                    event_type="SYNC_LIQUIDADOS_DIA",
                    company_id=cid,
                    success=True,
                    payload={
                        "dia": dia_str,
                        "returned": returned,
                        "updated": updated,
                        "already_liquidado": already,
                        "unmatched": unmatched[:100],
                    },
                )
                await db.commit()

            await sicredi_service.persist_token_cache(db, cid)
            await db.commit()

        logger.info("sicredi_reconcile_completed", total_updated=total_updated)


async def _sync_company_async(session_factory: TaskSessionFactory, company_id: str):
    from uuid import UUID

    from app.services import sicredi_service
    from app.services.sicredi_audit_service import DIRECTION_OUTBOUND, log_sicredi_event

    cid = UUID(company_id) if isinstance(company_id, str) else company_id

    async with session_factory() as db:
        try:
            sicredi_client = await sicredi_service.get_sicredi_client(db, cid)
        except Exception as exc:
            # Emit a SYNC_RUN so an on-demand trigger always produces a visible
            # result (the frontend polls for it) even when the client can't load.
            logger.warning("sicredi_sync_no_client", company_id=str(cid), error=str(exc))
            await log_sicredi_event(
                db,
                direction=DIRECTION_OUTBOUND,
                event_type="SYNC_RUN",
                company_id=cid,
                success=False,
                payload={
                    "checked": 0,
                    "updated": 0,
                    "consult_errors": 0,
                    "write_errors": 0,
                    "unknown_situacoes": [],
                    "error_samples": [{"error": f"Falha ao carregar credencial Sicredi: {exc}", "nosso_numero": ""}],
                },
            )
            await db.commit()
            return

        try:
            await sync_company_open_boletos(db, sicredi_client, cid)
            await sicredi_service.persist_token_cache(db, cid)
            await db.commit()
        except Exception as exc:
            logger.exception("sicredi_sync_company_failed", company_id=str(cid))
            await db.rollback()
            await _log_sync_failure(db, cid, f"Falha na sincronização: {exc}")


@celery.task(name="app.tasks.sicredi_sync_tasks.sync_open_boletos")
def sync_open_boletos():
    """Reconcile open boletos with Sicredi (catches missed webhooks)."""
    run_in_task_loop(_sync_open_boletos_async)


@celery.task(name="app.tasks.sicredi_sync_tasks.sync_boletos_for_company")
def sync_boletos_for_company(company_id: str):
    """On-demand reconcile for a single company (triggered from the admin UI)."""
    run_in_task_loop(lambda sf: _sync_company_async(sf, company_id))


@celery.task(name="app.tasks.sicredi_sync_tasks.reconcile_liquidados")
def reconcile_liquidados():
    """Pull Sicredi's liquidated-boletos batch for yesterday+today and mark them paid."""
    run_in_task_loop(_reconcile_liquidados_async)
