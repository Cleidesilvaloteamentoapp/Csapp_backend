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
        .limit(_MAX_PER_COMPANY)
    )).scalars().all()

    updated = 0
    consult_errors = 0
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
        except SicrediError as exc:
            consult_errors += 1
            detail = str(exc.detail or exc)
            status_code = getattr(exc, "status_code", None)
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

        situacao = (data.situacao or "").upper()
        mapped = _SITUACAO_MAP.get(situacao)
        if not mapped:
            if situacao:
                unknown_situacoes.add(situacao)
            continue
        new_status = BoletoStatus(mapped)
        if new_status == boleto.status:
            continue

        if new_status == BoletoStatus.LIQUIDADO:
            await mark_boleto_liquidado(db, boleto, source="sync_open_boletos")
        else:
            boleto.status = new_status
            if situacao in ("BAIXADO", "BAIXADO POR SOLICITACAO"):
                if boleto.writeoff_type != WriteoffType.MANUAL_ADMIN:
                    boleto.writeoff_type = WriteoffType.BAIXA_EXTERNA
                    boleto.writeoff_reason = (
                        f"Baixa externa via Sicredi (situacao: {data.situacao}). "
                        "Sincronizado por tarefa periódica."
                    )
        updated += 1

    summary = {
        "checked": len(open_boletos),
        "updated": updated,
        "consult_errors": consult_errors,
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
                continue

            summary = await sync_company_open_boletos(db, sicredi_client, cid)
            total_synced += summary["updated"]

            await sicredi_service.persist_token_cache(db, cid)
            await db.commit()

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
                    "unknown_situacoes": [],
                    "error_samples": [{"error": f"Falha ao carregar credencial Sicredi: {exc}", "nosso_numero": ""}],
                },
            )
            await db.commit()
            return

        await sync_company_open_boletos(db, sicredi_client, cid)
        await sicredi_service.persist_token_cache(db, cid)
        await db.commit()


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
