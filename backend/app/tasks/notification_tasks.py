
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


# ---------------------------------------------------------------------------
# WhatsApp payment reminders (parallel to email reminders)
# ---------------------------------------------------------------------------

async def _send_whatsapp_reminders_async():
    """Send WhatsApp reminders: 7 days before, on due date, 1 day after."""
    from sqlalchemy import select
    from app.core.database import async_session_factory
    from app.models.client import Client
    from app.models.client_lot import ClientLot
    from app.models.enums import InvoiceStatus
    from app.models.invoice import Invoice
    from app.services.whatsapp_service import (
        notify_invoice_due,
        notify_invoice_overdue,
    )

    today = date.today()
    reminder_7d = today + timedelta(days=7)
    overdue_1d = today - timedelta(days=1)

    async with async_session_factory() as db:
        # 7-day WhatsApp reminders
        rows = await db.execute(
            select(Invoice, Client)
            .join(ClientLot, ClientLot.id == Invoice.client_lot_id)
            .join(Client, Client.id == ClientLot.client_id)
            .where(
                Invoice.status == InvoiceStatus.PENDING,
                Invoice.due_date == reminder_7d,
            )
        )
        sent = 0
        for inv, client in rows.all():
            if not client.phone:
                continue
            try:
                await notify_invoice_due(
                    to=client.phone,
                    name=client.full_name,
                    due_date=inv.due_date.isoformat(),
                    amount=str(inv.amount),
                    db=db,
                    company_id=client.company_id,
                )
                sent += 1
            except Exception as exc:
                logger.warning("whatsapp_reminder_failed", client_id=str(client.id), error=str(exc))

        # Due-date WhatsApp reminders
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
            if not client.phone:
                continue
            try:
                await notify_invoice_due(
                    to=client.phone,
                    name=client.full_name,
                    due_date=inv.due_date.isoformat(),
                    amount=str(inv.amount),
                    db=db,
                    company_id=client.company_id,
                )
                sent += 1
            except Exception as exc:
                logger.warning("whatsapp_reminder_failed", client_id=str(client.id), error=str(exc))

        # 1-day overdue WhatsApp alerts
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
            if not client.phone:
                continue
            try:
                await notify_invoice_overdue(
                    to=client.phone,
                    name=client.full_name,
                    due_date=inv.due_date.isoformat(),
                    amount=str(inv.amount),
                    db=db,
                    company_id=client.company_id,
                )
                sent += 1
            except Exception as exc:
                logger.warning("whatsapp_overdue_failed", client_id=str(client.id), error=str(exc))

        logger.info("whatsapp_reminders_sent", count=sent, date=today.isoformat())


@celery.task(bind=True, max_retries=3, default_retry_delay=300)
def send_whatsapp_reminders(self):
    """Daily task: send WhatsApp payment reminders and overdue alerts."""
    try:
        _run_async(_send_whatsapp_reminders_async())
    except Exception as exc:
        logger.error("whatsapp_reminders_failed", error=str(exc))
        self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Overdue escalation (30 / 60 / 90 day alerts + auto-distrato)
# ---------------------------------------------------------------------------

async def _overdue_escalation_async():
    """Escalation alerts at 30, 60, 90 days overdue.

    At 90+ days: triggers automatic rescission (distrato) process and notifies
    the client via email + WhatsApp.
    """
    from sqlalchemy import select, func, update
    from app.core.database import async_session_factory
    from app.models.client import Client
    from app.models.client_lot import ClientLot
    from app.models.enums import (
        ClientLotStatus,
        ClientStatus,
        ContractEventType,
        InvoiceStatus,
    )
    from app.models.invoice import Invoice
    from app.services.contract_history_service import record_event
    from app.services.email_service import send_admin_alert, send_rescission_alert
    from app.services.whatsapp_service import send_whatsapp_message

    today = date.today()

    async with async_session_factory() as db:
        # Find clients with overdue invoices grouped by oldest due date
        rows = await db.execute(
            select(
                Client.id.label("client_id"),
                Client.full_name,
                Client.email,
                Client.phone,
                Client.company_id,
                ClientLot.id.label("client_lot_id"),
                func.min(Invoice.due_date).label("oldest_due"),
            )
            .join(ClientLot, ClientLot.client_id == Client.id)
            .join(Invoice, Invoice.client_lot_id == ClientLot.id)
            .where(
                Invoice.status == InvoiceStatus.OVERDUE,
                ClientLot.status == ClientLotStatus.ACTIVE,
            )
            .group_by(
                Client.id, Client.full_name, Client.email, Client.phone,
                Client.company_id, ClientLot.id,
            )
        )

        auto_distrato_count = 0

        for row in rows.all():
            days_overdue = (today - row.oldest_due).days

            if days_overdue < 30:
                continue

            # 30-day alert
            if 30 <= days_overdue < 31:
                try:
                    await send_admin_alert(
                        company_id=str(row.company_id),
                        subject=f"30 dias de atraso: {row.full_name}",
                        message=(
                            f"O cliente {row.full_name} está com {days_overdue} dias de atraso. "
                            f"Verificar possibilidade de acordo."
                        ),
                    )
                except Exception as exc:
                    logger.warning("30d_alert_failed", client_id=str(row.client_id), error=str(exc))

            # 60-day alert
            elif 60 <= days_overdue < 61:
                try:
                    await send_admin_alert(
                        company_id=str(row.company_id),
                        subject=f"60 dias de atraso: {row.full_name}",
                        message=(
                            f"ATENÇÃO: O cliente {row.full_name} está com {days_overdue} dias de atraso. "
                            f"Notificação extrajudicial recomendada."
                        ),
                    )
                    if row.email:
                        await send_rescission_alert(
                            to=row.email,
                            name=row.full_name,
                            days_overdue=days_overdue,
                        )
                except Exception as exc:
                    logger.warning("60d_alert_failed", client_id=str(row.client_id), error=str(exc))

            # 90-day: auto-distrato
            elif days_overdue >= 90:
                try:
                    # Mark client as DEFAULTER if not already
                    await db.execute(
                        update(Client)
                        .where(Client.id == row.client_id)
                        .values(status=ClientStatus.DEFAULTER)
                    )

                    # Mark client_lot as RESCINDED
                    await db.execute(
                        update(ClientLot)
                        .where(ClientLot.id == row.client_lot_id)
                        .values(status=ClientLotStatus.RESCINDED)
                    )

                    # Record contract history event
                    await record_event(
                        db,
                        company_id=row.company_id,
                        client_id=row.client_id,
                        client_lot_id=row.client_lot_id,
                        event_type=ContractEventType.AUTO_RESCISSION,
                        description=(
                            f"Distrato automático por inadimplência de {days_overdue} dias. "
                            f"Parcela mais antiga vencida em {row.oldest_due.isoformat()}."
                        ),
                        metadata_json={
                            "days_overdue": days_overdue,
                            "oldest_due_date": row.oldest_due.isoformat(),
                            "triggered_by": "system_auto_distrato",
                        },
                    )

                    # Notify client via email
                    if row.email:
                        await send_rescission_alert(
                            to=row.email,
                            name=row.full_name,
                            days_overdue=days_overdue,
                        )

                    # Notify client via WhatsApp
                    if row.phone:
                        await send_whatsapp_message(
                            to=row.phone,
                            body=(
                                f"Prezado(a) {row.full_name}, informamos que seu contrato "
                                f"foi rescindido automaticamente devido a {days_overdue} dias "
                                f"de inadimplência. Entre em contato para regularização."
                            ),
                            db=db,
                            company_id=row.company_id,
                        )

                    # Admin alert
                    await send_admin_alert(
                        company_id=str(row.company_id),
                        subject=f"DISTRATO AUTOMÁTICO: {row.full_name}",
                        message=(
                            f"Distrato automático aplicado ao cliente {row.full_name} "
                            f"por {days_overdue} dias de inadimplência. "
                            f"Lote liberado para revenda."
                        ),
                    )

                    auto_distrato_count += 1

                except Exception as exc:
                    logger.error(
                        "auto_distrato_failed",
                        client_id=str(row.client_id),
                        client_lot_id=str(row.client_lot_id),
                        error=str(exc),
                    )

        await db.commit()
        logger.info(
            "overdue_escalation_completed",
            date=today.isoformat(),
            auto_distrato_count=auto_distrato_count,
        )


@celery.task(bind=True, max_retries=3, default_retry_delay=600)
def overdue_escalation(self):
    """Daily task: escalation alerts at 30/60/90 days + auto-distrato at 90+ days."""
    try:
        _run_async(_overdue_escalation_async())
    except Exception as exc:
        logger.error("overdue_escalation_failed", error=str(exc))
        self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Cycle completion notification
# ---------------------------------------------------------------------------

async def _notify_cycle_completion_async():
    """Create CycleApproval records when a 12-installment cycle completes."""
    from sqlalchemy import select, func
    from app.core.database import async_session_factory
    from app.models.client_lot import ClientLot
    from app.models.cycle_approval import CycleApproval
    from app.models.enums import ClientLotStatus, CycleApprovalStatus, InvoiceStatus
    from app.models.invoice import Invoice
    from app.services.email_service import send_admin_alert

    async with async_session_factory() as db:
        rows = await db.execute(
            select(ClientLot).where(ClientLot.status == ClientLotStatus.ACTIVE)
        )
        active_lots = rows.scalars().all()
        created = 0

        for cl in active_lots:
            cycle_size = 12
            cycle_start = (cl.current_cycle - 1) * cycle_size + 1
            cycle_end = cl.current_cycle * cycle_size

            # Count paid invoices in current cycle
            paid_q = await db.execute(
                select(func.count()).where(
                    Invoice.client_lot_id == cl.id,
                    Invoice.installment_number >= cycle_start,
                    Invoice.installment_number <= cycle_end,
                    Invoice.status == InvoiceStatus.PAID,
                )
            )
            paid_count = paid_q.scalar() or 0

            if paid_count < cycle_size:
                continue

            total = cl.total_installments or 1
            if cycle_end >= total:
                continue  # All installments done, no next cycle needed

            # Check if approval already exists for next cycle
            next_cycle = cl.current_cycle + 1
            existing = await db.execute(
                select(CycleApproval).where(
                    CycleApproval.client_lot_id == cl.id,
                    CycleApproval.cycle_number == next_cycle,
                )
            )
            if existing.scalar_one_or_none():
                continue

            # Create pending approval
            approval = CycleApproval(
                company_id=cl.company_id,
                client_lot_id=cl.id,
                cycle_number=next_cycle,
                status=CycleApprovalStatus.PENDING,
                previous_installment_value=cl.current_installment_value or (cl.total_value / total),
            )
            db.add(approval)
            created += 1

            # Send admin alert
            try:
                await send_admin_alert(
                    company_id=str(cl.company_id),
                    subject=f"Ciclo {cl.current_cycle} concluído — aprovação pendente",
                    message=(
                        f"O ciclo {cl.current_cycle} do contrato (lote ID: {cl.id}) foi concluído. "
                        f"Uma solicitação de aprovação para o ciclo {next_cycle} foi criada. "
                        f"Valor atual da parcela: R${cl.current_installment_value}."
                    ),
                )
            except Exception as exc:
                logger.warning("cycle_completion_alert_failed", cl_id=str(cl.id), error=str(exc))

        await db.commit()
        logger.info("cycle_completion_check", approvals_created=created)


@celery.task(bind=True, max_retries=3, default_retry_delay=300)
def check_cycle_completions(self):
    """Daily task: check for completed 12-installment cycles and create approval requests."""
    try:
        _run_async(_notify_cycle_completion_async())
    except Exception as exc:
        logger.error("cycle_completion_check_failed", error=str(exc))
        self.retry(exc=exc)
