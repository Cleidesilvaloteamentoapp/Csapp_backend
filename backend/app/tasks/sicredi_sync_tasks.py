"""Periodic task to reconcile local boleto status with Sicredi.

Covers the gap where a boleto is liquidated/baixado at the bank but the webhook
was missed, leaving the local record stuck as NORMAL/VENCIDO ("em aberto").
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
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.models.boleto import Boleto
    from app.models.enums import BoletoStatus, InvoiceStatus, WriteoffType
    from app.models.invoice import Invoice
    from app.models.sicredi_credential import SicrediCredential
    from app.services import sicredi_service
    from app.services.sicredi.exceptions import SicrediError

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

            for boleto in open_boletos:
                try:
                    data = await sicredi_client.boletos.consultar_por_nosso_numero(
                        boleto.nosso_numero
                    )
                except SicrediError as exc:
                    logger.warning(
                        "sicredi_sync_consult_failed",
                        nosso_numero=boleto.nosso_numero,
                        error=str(exc.detail or exc),
                    )
                    continue

                situacao = (data.situacao or "").upper()
                mapped = _SITUACAO_MAP.get(situacao)
                if not mapped:
                    continue
                new_status = BoletoStatus(mapped)
                if new_status == boleto.status:
                    continue

                boleto.status = new_status
                if situacao in ("BAIXADO", "BAIXADO POR SOLICITACAO"):
                    if boleto.writeoff_type != WriteoffType.MANUAL_ADMIN:
                        boleto.writeoff_type = WriteoffType.BAIXA_EXTERNA
                        boleto.writeoff_reason = (
                            f"Baixa externa via Sicredi (situacao: {data.situacao}). "
                            "Sincronizado por tarefa periódica."
                        )
                if new_status == BoletoStatus.LIQUIDADO:
                    if not boleto.data_liquidacao:
                        boleto.data_liquidacao = datetime.now(timezone.utc).date()
                    if boleto.invoice_id:
                        inv = (await db.execute(
                            select(Invoice).where(Invoice.id == boleto.invoice_id)
                        )).scalar_one_or_none()
                        if inv and inv.status != InvoiceStatus.PAID:
                            inv.status = InvoiceStatus.PAID
                            inv.paid_at = datetime.now(timezone.utc)

                total_synced += 1

            await sicredi_service.persist_token_cache(db, cid)
            await db.commit()

        logger.info("sicredi_sync_completed", total_synced=total_synced)


@celery.task(name="app.tasks.sicredi_sync_tasks.sync_open_boletos")
def sync_open_boletos():
    """Reconcile open boletos with Sicredi (catches missed webhooks)."""
    run_in_task_loop(_sync_open_boletos_async)
