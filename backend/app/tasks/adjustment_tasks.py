
"""Celery tasks for annual IPCA adjustment and admin alerts."""

import asyncio
from datetime import date, timedelta
from decimal import Decimal

from app.tasks.celery_app import celery
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _apply_annual_adjustments_async():
    """Apply annual IPCA + fixed rate adjustments to active contracts.

    Rule: Valor da Parcela + 5% + IPCA acumulado dos últimos 12 meses.
    Only applies to contracts where the last 12-installment cycle is fully paid.
    """
    from sqlalchemy import select, func
    from app.core.database import async_session_factory
    from app.models.client_lot import ClientLot
    from app.models.enums import ClientLotStatus, ContractEventType, InvoiceStatus
    from app.models.invoice import Invoice
    from app.services.contract_history_service import record_event
    from app.services.ipca_service import get_ipca_accumulated_12_months, calculate_adjusted_value

    today = date.today()

    async with async_session_factory() as db:
        # Fetch IPCA for last 12 months
        ipca_pct = await get_ipca_accumulated_12_months(today)
        logger.info("annual_adjustment_ipca", ipca_pct=str(ipca_pct))

        if ipca_pct <= 0:
            logger.warning("annual_adjustment_skipped_no_ipca")
            return

        # Find active contracts that need adjustment (not adjusted this year)
        one_year_ago = today - timedelta(days=365)
        rows = await db.execute(
            select(ClientLot).where(
                ClientLot.status == ClientLotStatus.ACTIVE,
                # Only adjust if last adjustment was > 1 year ago or never adjusted
                ClientLot.last_adjustment_date.is_(None) | (ClientLot.last_adjustment_date <= one_year_ago),
            )
        )
        contracts = rows.scalars().all()
        adjusted_count = 0

        for cl in contracts:
            # Check if the last 12 invoices are all PAID (cycle lock)
            recent_invoices = await db.execute(
                select(Invoice)
                .where(
                    Invoice.client_lot_id == cl.id,
                    Invoice.status != InvoiceStatus.CANCELLED,
                )
                .order_by(Invoice.installment_number.desc())
                .limit(12)
            )
            recent = list(recent_invoices.scalars().all())

            if len(recent) < 12:
                continue  # Not enough invoices yet

            all_paid = all(inv.status == InvoiceStatus.PAID for inv in recent)
            if not all_paid:
                continue  # Cannot adjust — cycle not fully paid

            # Calculate adjustment
            current_value = cl.current_installment_value or (cl.total_value / cl.total_installments)
            fixed_rate = Decimal(str(cl.annual_adjustment_rate or Decimal("0.05"))) * Decimal("100")

            adj = calculate_adjusted_value(current_value, ipca_pct, fixed_rate)

            # Update contract
            cl.current_installment_value = adj["new_value"]
            cl.last_adjustment_date = today
            cl.current_cycle += 1
            cl.last_cycle_paid_at = today

            await record_event(
                db,
                company_id=cl.company_id,
                client_id=cl.client_id,
                client_lot_id=cl.id,
                event_type=ContractEventType.ADJUSTMENT,
                description=(
                    f"Reajuste anual aplicado (ciclo {cl.current_cycle}). "
                    f"IPCA: {ipca_pct}%, Taxa fixa: {fixed_rate}%. "
                    f"Valor anterior: R${adj['original_value']}, "
                    f"Novo valor: R${adj['new_value']}"
                ),
                amount=adj["new_value"],
                previous_value=str(adj["original_value"]),
                new_value=str(adj["new_value"]),
                metadata_json={
                    "ipca_pct": str(ipca_pct),
                    "fixed_rate_pct": str(fixed_rate),
                    "ipca_adjustment": str(adj["ipca_adjustment"]),
                    "fixed_adjustment": str(adj["fixed_adjustment"]),
                    "cycle": cl.current_cycle,
                },
            )

            adjusted_count += 1
            logger.info(
                "contract_adjusted",
                client_lot_id=str(cl.id),
                old_value=str(adj["original_value"]),
                new_value=str(adj["new_value"]),
            )

        await db.commit()
        logger.info("annual_adjustments_completed", count=adjusted_count)


@celery.task(bind=True, max_retries=3, default_retry_delay=600)
def apply_annual_adjustments(self):
    """Annual task: apply IPCA + fixed rate adjustment to eligible contracts."""
    try:
        _run_async(_apply_annual_adjustments_async())
    except Exception as exc:
        logger.error("annual_adjustment_failed", error=str(exc))
        self.retry(exc=exc)


async def _send_admin_alerts_async():
    """Send admin alerts for cycle completions and critical defaulters."""
    from sqlalchemy import select, func
    from app.core.database import async_session_factory
    from app.models.client import Client
    from app.models.client_lot import ClientLot
    from app.models.enums import ClientLotStatus, ClientStatus, InvoiceStatus
    from app.models.invoice import Invoice
    from app.services.email_service import send_admin_alert

    today = date.today()
    ninety_days_ago = today - timedelta(days=90)

    async with async_session_factory() as db:
        # Alert 1: Clients with 90+ days overdue (rescission trigger)
        critical_rows = await db.execute(
            select(Client.id, Client.full_name, Client.company_id, func.min(Invoice.due_date).label("oldest_due"))
            .join(ClientLot, ClientLot.client_id == Client.id)
            .join(Invoice, Invoice.client_lot_id == ClientLot.id)
            .where(
                Client.status == ClientStatus.DEFAULTER,
                Invoice.status == InvoiceStatus.OVERDUE,
                Invoice.due_date <= ninety_days_ago,
            )
            .group_by(Client.id, Client.full_name, Client.company_id)
        )
        critical_clients = critical_rows.all()
        for row in critical_clients:
            days = (today - row.oldest_due).days
            try:
                await send_admin_alert(
                    company_id=str(row.company_id),
                    subject=f"ALERTA: Cliente {row.full_name} com {days} dias de atraso",
                    message=(
                        f"O cliente {row.full_name} está com {days} dias de inadimplência. "
                        f"De acordo com a política, contratos com 90+ dias de atraso "
                        f"devem iniciar processo de rescisão."
                    ),
                )
            except Exception as exc:
                logger.warning("admin_alert_failed", client_id=str(row.id), error=str(exc))

        # Alert 2: Clients who completed a 12-invoice cycle
        cycle_complete_rows = await db.execute(
            select(
                ClientLot.id.label("cl_id"),
                ClientLot.company_id,
                ClientLot.current_cycle,
                Client.full_name,
            )
            .join(Client, Client.id == ClientLot.client_id)
            .where(ClientLot.status == ClientLotStatus.ACTIVE)
        )
        for row in cycle_complete_rows.all():
            # Check if last 12 invoices all paid
            inv_rows = await db.execute(
                select(Invoice)
                .where(Invoice.client_lot_id == row.cl_id)
                .order_by(Invoice.installment_number.desc())
                .limit(12)
            )
            recent = list(inv_rows.scalars().all())
            if len(recent) == 12 and all(inv.status == InvoiceStatus.PAID for inv in recent):
                # Check if the most recent was paid in the last 7 days (avoid repeat alerts)
                last_paid = max((inv.paid_at for inv in recent if inv.paid_at), default=None)
                if last_paid and (today - last_paid.date()).days <= 7:
                    try:
                        await send_admin_alert(
                            company_id=str(row.company_id),
                            subject=f"Ciclo {row.current_cycle} concluído: {row.full_name}",
                            message=(
                                f"O cliente {row.full_name} completou o ciclo {row.current_cycle} "
                                f"de 12 parcelas. Reajuste anual deve ser aplicado."
                            ),
                        )
                    except Exception as exc:
                        logger.warning("cycle_alert_failed", cl_id=str(row.cl_id), error=str(exc))

        logger.info("admin_alerts_completed", date=today.isoformat())


@celery.task(bind=True, max_retries=3, default_retry_delay=300)
def send_admin_alerts(self):
    """Daily task: send admin alerts for critical situations."""
    try:
        _run_async(_send_admin_alerts_async())
    except Exception as exc:
        logger.error("admin_alerts_failed", error=str(exc))
        self.retry(exc=exc)
