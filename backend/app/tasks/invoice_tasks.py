
"""Celery tasks for invoice management."""

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from app.tasks._async_helpers import TaskSessionFactory, run_in_task_loop
from app.tasks.celery_app import celery
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def _check_overdue_invoices_async(session_factory: TaskSessionFactory):
    """Find pending invoices past due date, mark as overdue, flag defaulters."""
    from sqlalchemy import select, update
    from app.models.client import Client
    from app.models.client_lot import ClientLot
    from app.models.enums import ClientStatus, InvoiceStatus
    from app.models.invoice import Invoice

    async with session_factory() as db:
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
        run_in_task_loop(_check_overdue_invoices_async)
    except Exception as exc:
        logger.error("check_overdue_failed", error=str(exc))
        self.retry(exc=exc)


async def _generate_monthly_invoices_async(session_factory: TaskSessionFactory):
    """Top up invoices for active client_lots within their current cycle.

    CYCLE BOUNDARY RULE: this task never starts a new 12-installment cycle.
    Crossing that boundary reprices the installment and is released by an admin
    on /admin/cycle-approvals, which generates the next batch itself.
    """
    from sqlalchemy import select
    from app.models.client_lot import ClientLot
    from app.models.enums import ClientLotStatus, InvoiceStatus
    from app.models.invoice import Invoice

    async with session_factory() as db:
        rows = await db.execute(
            select(ClientLot).where(ClientLot.status == ClientLotStatus.ACTIVE)
        )
        active_lots = rows.scalars().all()
        created = 0
        skipped_cycle_lock = 0

        for cl in active_lots:
            total_installments = cl.total_installments or 1

            # Count existing non-cancelled invoices
            inv_rows = await db.execute(
                select(Invoice).where(
                    Invoice.client_lot_id == cl.id,
                    Invoice.status != InvoiceStatus.CANCELLED,
                )
            )
            all_invoices = list(inv_rows.scalars().all())
            existing = len(all_invoices)

            if existing >= total_installments:
                continue  # All installments already generated

            # Cycle boundary: everything past it belongs to the approval flow.
            cycle_size = 12
            current_cycle_end = cl.current_cycle * cycle_size

            if existing >= current_cycle_end:
                # Crossing into the next cycle is the admin's decision, not this
                # task's: the next 12 installments carry a repriced value that an
                # admin approves on /admin/cycle-approvals, and approve_cycle
                # generates them itself. Emitting one here would bill the client
                # at the stale value and bypass the approval entirely.
                skipped_cycle_lock += 1
                continue

            # Find last invoice due date
            last_inv = await db.execute(
                select(Invoice)
                .where(
                    Invoice.client_lot_id == cl.id,
                    Invoice.status != InvoiceStatus.CANCELLED,
                )
                .order_by(Invoice.due_date.desc())
                .limit(1)
            )
            last = last_inv.scalar_one_or_none()
            # relativedelta preserves the day-of-month across months; timedelta(30) drifts.
            next_due = (
                (last.due_date + relativedelta(months=1))
                if last
                else date.today() + relativedelta(months=1)
            )

            # Use current_installment_value if set (after adjustment), else calculate
            installment_value = cl.current_installment_value or (cl.total_value / total_installments)

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
        logger.info(
            "monthly_invoices_generated",
            count=created,
            skipped_cycle_lock=skipped_cycle_lock,
        )


@celery.task(bind=True, max_retries=3, default_retry_delay=300)
def generate_monthly_invoices(self):
    """Monthly task: generate upcoming invoices for active lots."""
    try:
        run_in_task_loop(_generate_monthly_invoices_async)
    except Exception as exc:
        logger.error("generate_monthly_failed", error=str(exc))
        self.retry(exc=exc)

