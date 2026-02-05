"""Celery tasks for invoice management and Asaas sync."""

import asyncio
from datetime import date, datetime, timedelta, timezone

from app.tasks.celery_app import celery
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _run_async(coro):
    """Helper to run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _check_overdue_invoices_async():
    """Find pending invoices past due date, mark as overdue, flag defaulters."""
    from sqlalchemy import select, update
    from app.core.database import async_session_factory
    from app.models.client import Client
    from app.models.client_lot import ClientLot
    from app.models.enums import ClientStatus, InvoiceStatus
    from app.models.invoice import Invoice

    async with async_session_factory() as db:
        today = date.today()

        # Mark pending invoices past due date as overdue
        await db.execute(
            update(Invoice)
            .where(
                Invoice.status == InvoiceStatus.PENDING,
                Invoice.due_date < today,
            )
            .values(status=InvoiceStatus.OVERDUE)
        )

        # Identify clients with 3+ months of overdue invoices
        three_months_ago = today - timedelta(days=90)
        rows = await db.execute(
            select(Client.id)
            .join(ClientLot, ClientLot.client_id == Client.id)
            .join(Invoice, Invoice.client_lot_id == ClientLot.id)
            .where(
                Invoice.status == InvoiceStatus.OVERDUE,
                Invoice.due_date <= three_months_ago,
            )
            .group_by(Client.id)
        )
        defaulter_ids = [r[0] for r in rows.all()]

        if defaulter_ids:
            await db.execute(
                update(Client)
                .where(Client.id.in_(defaulter_ids))
                .values(status=ClientStatus.DEFAULTER)
            )
            logger.info("defaulters_flagged", count=len(defaulter_ids))

        await db.commit()
        logger.info("overdue_check_completed", date=today.isoformat())


@celery.task(bind=True, max_retries=3, default_retry_delay=300)
def check_overdue_invoices(self):
    """Daily task: mark overdue invoices and flag defaulters."""
    try:
        _run_async(_check_overdue_invoices_async())
    except Exception as exc:
        logger.error("check_overdue_failed", error=str(exc))
        self.retry(exc=exc)


async def _generate_monthly_invoices_async():
    """Generate next month's invoices for active client_lots."""
    from sqlalchemy import select
    from app.core.database import async_session_factory
    from app.models.client_lot import ClientLot
    from app.models.enums import ClientLotStatus, InvoiceStatus
    from app.models.invoice import Invoice

    async with async_session_factory() as db:
        rows = await db.execute(
            select(ClientLot).where(ClientLot.status == ClientLotStatus.ACTIVE)
        )
        active_lots = rows.scalars().all()
        created = 0

        for cl in active_lots:
            plan = cl.payment_plan or {}
            total_installments = int(plan.get("installments", 1))

            # Count existing invoices
            inv_count = await db.execute(
                select(Invoice).where(Invoice.client_lot_id == cl.id)
            )
            existing = len(inv_count.scalars().all())

            if existing >= total_installments:
                continue  # All installments already generated

            # Find last invoice due date
            last_inv = await db.execute(
                select(Invoice)
                .where(Invoice.client_lot_id == cl.id)
                .order_by(Invoice.due_date.desc())
                .limit(1)
            )
            last = last_inv.scalar_one_or_none()
            next_due = (last.due_date + timedelta(days=30)) if last else date.today() + timedelta(days=30)

            installment_value = cl.total_value / total_installments

            invoice = Invoice(
                company_id=cl.company_id,
                client_lot_id=cl.id,
                due_date=next_due,
                amount=installment_value,
                installment_number=existing + 1,
                status=InvoiceStatus.PENDING,
            )
            db.add(invoice)
            created += 1

        await db.commit()
        logger.info("monthly_invoices_generated", count=created)


@celery.task(bind=True, max_retries=3, default_retry_delay=300)
def generate_monthly_invoices(self):
    """Monthly task: generate upcoming invoices for active lots."""
    try:
        _run_async(_generate_monthly_invoices_async())
    except Exception as exc:
        logger.error("generate_monthly_failed", error=str(exc))
        self.retry(exc=exc)


async def _sync_payment_status_async():
    """Sync payment status with Asaas for pending invoices."""
    from sqlalchemy import select
    from app.core.database import async_session_factory
    from app.models.enums import InvoiceStatus
    from app.models.invoice import Invoice
    from app.services.asaas_service import get_payment

    async with async_session_factory() as db:
        rows = await db.execute(
            select(Invoice).where(
                Invoice.asaas_payment_id.isnot(None),
                Invoice.status.in_([InvoiceStatus.PENDING, InvoiceStatus.OVERDUE]),
            )
        )
        invoices = rows.scalars().all()
        synced = 0

        for inv in invoices:
            try:
                payment = await get_payment(inv.asaas_payment_id)
                asaas_status = payment.get("status", "")

                if asaas_status in ("RECEIVED", "CONFIRMED"):
                    inv.status = InvoiceStatus.PAID
                    inv.paid_at = datetime.now(timezone.utc)
                    synced += 1
                elif asaas_status == "OVERDUE" and inv.status != InvoiceStatus.OVERDUE:
                    inv.status = InvoiceStatus.OVERDUE
                    synced += 1
            except Exception as exc:
                logger.warning("sync_payment_error", invoice_id=str(inv.id), error=str(exc))

        await db.commit()
        logger.info("payment_sync_completed", synced=synced)


@celery.task(bind=True, max_retries=3, default_retry_delay=300)
def sync_payment_status(self):
    """Periodic task: sync pending/overdue invoices with Asaas."""
    try:
        _run_async(_sync_payment_status_async())
    except Exception as exc:
        logger.error("sync_payment_failed", error=str(exc))
        self.retry(exc=exc)
