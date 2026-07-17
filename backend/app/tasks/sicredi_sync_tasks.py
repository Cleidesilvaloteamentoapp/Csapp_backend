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


async def _sync_open_boletos_async(session_factory: TaskSessionFactory):
    from sqlalchemy import select

    from app.models.boleto import Boleto
    from app.models.enums import BoletoStatus, WriteoffType
    from app.models.sicredi_credential import SicrediCredential
    from app.services import sicredi_service
    from app.services.boleto_status_service import mark_boleto_liquidado
    from app.services.sicredi.exceptions import SicrediError
    from app.services.sicredi_audit_service import DIRECTION_OUTBOUND, log_sicredi_event

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

            open_boletos = (await db.execute(
                select(Boleto)
                .where(
                    Boleto.company_id == cid,
                    Boleto.status.in_([BoletoStatus.NORMAL, BoletoStatus.VENCIDO]),
                    Boleto.nosso_numero.isnot(None),
                )
                .limit(_MAX_PER_COMPANY)
            )).scalars().all()

            updated = 0
            consult_errors = 0
            unknown_situacoes: set[str] = set()

            for boleto in open_boletos:
                try:
                    data = await sicredi_client.boletos.consultar_por_nosso_numero(
                        boleto.nosso_numero
                    )
                except SicrediError as exc:
                    consult_errors += 1
                    logger.warning(
                        "sicredi_sync_consult_failed",
                        nosso_numero=boleto.nosso_numero,
                        error=str(exc.detail or exc),
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

            total_synced += updated

            # Heartbeat: proves the job ran for this company and how much it did.
            await log_sicredi_event(
                db,
                direction=DIRECTION_OUTBOUND,
                event_type="SYNC_RUN",
                company_id=cid,
                success=True,
                payload={
                    "checked": len(open_boletos),
                    "updated": updated,
                    "consult_errors": consult_errors,
                    "unknown_situacoes": sorted(unknown_situacoes),
                },
            )

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


@celery.task(name="app.tasks.sicredi_sync_tasks.sync_open_boletos")
def sync_open_boletos():
    """Reconcile open boletos with Sicredi (catches missed webhooks)."""
    run_in_task_loop(_sync_open_boletos_async)


@celery.task(name="app.tasks.sicredi_sync_tasks.reconcile_liquidados")
def reconcile_liquidados():
    """Pull Sicredi's liquidated-boletos batch for yesterday+today and mark them paid."""
    run_in_task_loop(_reconcile_liquidados_async)
