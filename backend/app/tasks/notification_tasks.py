"""Celery tasks for notifications (email + WhatsApp)."""

import asyncio
from datetime import date, timedelta

from app.tasks.celery_app import celery
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _send_payment_reminders_async():
    """Send reminders: 7 days before, on due date, and 1 day after."""
    from sqlalchemy import select
    from app.core.database import async_session_factory
    from app.models.client import Client
    from app.models.client_lot import ClientLot
    from app.models.enums import InvoiceStatus
    from app.models.invoice import Invoice
    from app.services.email_service import send_overdue_alert, send_payment_reminder

    today = date.today()
    reminder_7d = today + timedelta(days=7)
    overdue_1d = today - timedelta(days=1)

    async with async_session_factory() as db:
        # 7-day reminders
        rows = await db.execute(
            select(Invoice, Client)
            .join(ClientLot, ClientLot.id == Invoice.client_lot_id)
            .join(Client, Client.id == ClientLot.client_id)
            .where(
                Invoice.status == InvoiceStatus.PENDING,
                Invoice.due_date == reminder_7d,
            )
        )
        for inv, client in rows.all():
            await send_payment_reminder(
                to=client.email,
                name=client.full_name,
                due_date=inv.due_date.isoformat(),
                amount=str(inv.amount),
            )

        # Due-date reminders
        rows = await db.execute(
            select(Invoice, Client)
            .join(ClientLot, ClientLot.id == Invoice.client_lot_id)
            .join(Client, Client.id == ClientLot.client_id)
            .where(
                Invoice.status == InvoiceStatus.PENDING,
                Invoice.due_date == today,
            )
        )
        for inv, client in rows.all():
            await send_payment_reminder(
                to=client.email,
                name=client.full_name,
                due_date=inv.due_date.isoformat(),
                amount=str(inv.amount),
            )

        # 1-day overdue alerts
        rows = await db.execute(
            select(Invoice, Client)
            .join(ClientLot, ClientLot.id == Invoice.client_lot_id)
            .join(Client, Client.id == ClientLot.client_id)
            .where(
                Invoice.status == InvoiceStatus.OVERDUE,
                Invoice.due_date == overdue_1d,
            )
        )
        for inv, client in rows.all():
            await send_overdue_alert(
                to=client.email,
                name=client.full_name,
                due_date=inv.due_date.isoformat(),
                amount=str(inv.amount),
            )

        logger.info("payment_reminders_sent", date=today.isoformat())


@celery.task(bind=True, max_retries=3, default_retry_delay=300)
def send_payment_reminders(self):
    """Daily task: send payment reminders and overdue alerts."""
    try:
        _run_async(_send_payment_reminders_async())
    except Exception as exc:
        logger.error("send_reminders_failed", error=str(exc))
        self.retry(exc=exc)


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def notify_service_order_update(self, order_id: str, new_status: str):
    """Send notification when a service order status changes."""

    async def _notify():
        from sqlalchemy import select
        from app.core.database import async_session_factory
        from app.models.client import Client
        from app.models.service import ServiceOrder
        from app.services.email_service import send_service_order_update

        async with async_session_factory() as db:
            row = await db.execute(
                select(ServiceOrder, Client)
                .join(Client, Client.id == ServiceOrder.client_id)
                .where(ServiceOrder.id == order_id)
            )
            result = row.one_or_none()
            if not result:
                logger.warning("notify_os_not_found", order_id=order_id)
                return

            _order, client = result
            await send_service_order_update(
                to=client.email,
                name=client.full_name,
                order_id=order_id,
                new_status=new_status,
            )

    try:
        _run_async(_notify())
    except Exception as exc:
        logger.error("notify_os_failed", order_id=order_id, error=str(exc))
        self.retry(exc=exc)
