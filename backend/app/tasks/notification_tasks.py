
"""Celery tasks for notifications (email + WhatsApp)."""

from datetime import date, timedelta
from decimal import Decimal

from app.tasks._async_helpers import TaskSessionFactory, run_in_task_loop
from app.tasks.celery_app import celery
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def _send_payment_reminders_async(session_factory: TaskSessionFactory):
    """Send reminders: 7 days before, on due date, and 1 day after."""
    from sqlalchemy import select
    from app.models.client import Client
    from app.models.client_lot import ClientLot
    from app.models.enums import InvoiceStatus
    from app.models.invoice import Invoice
    from app.services.email_service import send_overdue_alert, send_payment_reminder

    today = date.today()
    reminder_7d = today + timedelta(days=7)
    overdue_1d = today - timedelta(days=1)

    async with session_factory() as db:
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
        run_in_task_loop(_send_payment_reminders_async)
    except Exception as exc:
        logger.error("send_reminders_failed", error=str(exc))
        self.retry(exc=exc)


async def _notify_service_order_update_async(
    session_factory: TaskSessionFactory, order_id: str, new_status: str
):
    from sqlalchemy import select
    from app.models.client import Client
    from app.models.service import ServiceOrder
    from app.services.email_service import send_service_order_update
    from app.services.notification_settings_service import get_or_create as get_notif_settings
    from app.services.whatsapp_service import notify_service_order

    async with session_factory() as db:
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

        # WhatsApp to client if enabled
        try:
            ns = await get_notif_settings(db, client.company_id)
            if ns.notify_client_service and client.phone:
                await notify_service_order(
                    to=client.phone,
                    name=client.full_name,
                    status=new_status,
                    db=db,
                    company_id=client.company_id,
                )
        except Exception as exc:
            logger.warning("service_order_whatsapp_failed", order_id=order_id, error=str(exc))


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def notify_service_order_update(self, order_id: str, new_status: str):
    """Send notification when a service order status changes."""
    try:
        run_in_task_loop(
            lambda sf: _notify_service_order_update_async(sf, order_id, new_status)
        )
    except Exception as exc:
        logger.error("notify_os_failed", order_id=order_id, error=str(exc))
        self.retry(exc=exc)


# ---------------------------------------------------------------------------
# WhatsApp payment reminders (parallel to email reminders)
# ---------------------------------------------------------------------------

async def _send_whatsapp_reminders_async(session_factory: TaskSessionFactory):
    """Send WhatsApp reminders: 7 days before, on due date, 1 day after."""
    from sqlalchemy import select
    from app.models.client import Client
    from app.models.client_lot import ClientLot
    from app.models.enums import InvoiceStatus
    from app.models.invoice import Invoice
    from app.services.notification_settings_service import get_or_create as get_notif_settings
    from app.services.whatsapp_service import (
        notify_invoice_due,
        notify_invoice_overdue,
    )

    today = date.today()
    reminder_7d = today + timedelta(days=7)
    overdue_1d = today - timedelta(days=1)

    # Cache settings per company to avoid repeated DB lookups
    _settings_cache: dict = {}

    async def _get_settings(db, company_id):
        key = str(company_id)
        if key not in _settings_cache:
            _settings_cache[key] = await get_notif_settings(db, company_id)
        return _settings_cache[key]

    async with session_factory() as db:
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
                ns = await _get_settings(db, client.company_id)
                if not ns.notify_client_due_reminder:
                    continue
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
                ns = await _get_settings(db, client.company_id)
                if not ns.notify_client_due_reminder:
                    continue
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
                ns = await _get_settings(db, client.company_id)
                if not ns.notify_client_overdue:
                    continue
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
        run_in_task_loop(_send_whatsapp_reminders_async)
    except Exception as exc:
        logger.error("whatsapp_reminders_failed", error=str(exc))
        self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Overdue escalation (30 / 60 / 90 day alerts + auto-distrato)
# ---------------------------------------------------------------------------

async def _overdue_escalation_async(session_factory: TaskSessionFactory):
    """Escalation alerts at 30, 60, 90 days overdue.

    At 90+ days: triggers automatic rescission (distrato) process and notifies
    the client via email + WhatsApp.
    """
    from sqlalchemy import select, func, update
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
    from app.services.rescission_service import trigger_automatic_rescission

    today = date.today()

    # Contract triggers for rescission: >90 days overdue OR 3+ overdue parcelas.
    OVERDUE_PARCELAS_LIMIT = 3

    async with session_factory() as db:
        # Find clients with overdue invoices: oldest due date + how many are overdue.
        rows = await db.execute(
            select(
                Client.id.label("client_id"),
                Client.full_name,
                Client.email,
                Client.phone,
                Client.company_id,
                ClientLot.id.label("client_lot_id"),
                func.min(Invoice.due_date).label("oldest_due"),
                func.count(Invoice.id).label("overdue_count"),
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
            overdue_count = row.overdue_count or 0
            # Either trigger rescinds the contract (per the contract clauses).
            should_rescind = days_overdue >= 90 or overdue_count >= OVERDUE_PARCELAS_LIMIT

            if days_overdue < 30 and not should_rescind:
                continue

            # Rescission trigger (>90 days OR 3+ overdue parcelas): create a
            # PENDING, REVERSIBLE rescission — never hard-delete. The client is
            # treated as inadimplente and warned of the risk of losing the lot;
            # the admin approves (finalize) or reverts (after negotiation).
            if should_rescind:
                try:
                    reason = (
                        f"Inadimplência: {overdue_count} parcela(s) em atraso, "
                        f"{days_overdue} dias desde o vencimento mais antigo "
                        f"({row.oldest_due.isoformat()})."
                    )
                    rescission = await trigger_automatic_rescission(
                        db,
                        row.company_id,
                        client_id=row.client_id,
                        client_lot_id=row.client_lot_id,
                        reason=reason,
                        metadata={
                            "days_overdue": days_overdue,
                            "overdue_count": overdue_count,
                            "oldest_due_date": row.oldest_due.isoformat(),
                        },
                    )
                    if rescission is None:
                        continue  # already has an open rescission

                    # Warn the client of the risk (contract not yet rescinded).
                    if row.email:
                        await send_rescission_alert(
                            to=row.email, name=row.full_name, days_overdue=days_overdue,
                        )
                    if row.phone:
                        await send_whatsapp_message(
                            to=row.phone,
                            body=(
                                f"Prezado(a) {row.full_name}, seu contrato está em processo de "
                                f"rescisão por inadimplência ({overdue_count} parcela(s), {days_overdue} dias). "
                                f"Entre em contato URGENTE para negociar e evitar a perda do lote."
                            ),
                            db=db,
                            company_id=row.company_id,
                        )

                    # Admin alert: pending approval (reversible).
                    await send_admin_alert(
                        company_id=str(row.company_id),
                        subject=f"RESCISÃO PENDENTE: {row.full_name}",
                        message=(
                            f"Rescisão automática criada para {row.full_name} "
                            f"({overdue_count} parcela(s) em atraso, {days_overdue} dias). "
                            f"Cobrança suspensa. Aprove para liberar o lote ou reverta após negociação."
                        ),
                        db=db,
                    )
                    auto_distrato_count += 1
                except Exception as exc:
                    logger.error(
                        "auto_rescission_failed",
                        client_id=str(row.client_id),
                        client_lot_id=str(row.client_lot_id),
                        error=str(exc),
                    )
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
                        db=db,
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
                        db=db,
                    )
                    if row.email:
                        await send_rescission_alert(
                            to=row.email,
                            name=row.full_name,
                            days_overdue=days_overdue,
                        )
                except Exception as exc:
                    logger.warning("60d_alert_failed", client_id=str(row.client_id), error=str(exc))

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
        run_in_task_loop(_overdue_escalation_async)
    except Exception as exc:
        logger.error("overdue_escalation_failed", error=str(exc))
        self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Cycle completion notification
# ---------------------------------------------------------------------------

# How many days before the cycle's last due date the renewal is raised. The
# admin needs lead time to review the index and release the next 12 boletos
# before billing runs dry; waiting for full settlement left no runway at all.
CYCLE_LEAD_DAYS = 45


async def _notify_cycle_completion_async(session_factory: TaskSessionFactory):
    """Raise CycleApproval records ahead of each 12-installment cycle's end.

    The approval is raised on schedule, not on settlement: a single unpaid
    installment used to hide the renewal entirely. Settlement is recorded on the
    approval instead (`unpaid_count` / `overdue_amount`), where it gates the
    Approve button and can be overridden deliberately.
    """
    from sqlalchemy import func, select
    from app.models.client_lot import ClientLot
    from app.models.cycle_approval import CycleApproval
    from app.models.enums import (
        ClientLotStatus,
        CycleApprovalStatus,
        InvoiceStatus,
        NotificationType,
    )
    from app.models.invoice import Invoice
    from app.services.admin_notify_service import notify_admins
    from app.services.client_lot_service import get_boleto_liquidated_invoice_ids
    from app.services.email_service import send_admin_alert

    today = date.today()

    async with session_factory() as db:
        rows = await db.execute(
            select(ClientLot).where(ClientLot.status == ClientLotStatus.ACTIVE)
        )
        active_lots = rows.scalars().all()
        created = 0
        completed = 0

        for cl in active_lots:
            cycle_size = 12
            cycle_start = (cl.current_cycle - 1) * cycle_size
            cycle_end = cl.current_cycle * cycle_size
            total = cl.total_installments or 1

            cycle_rows = await db.execute(
                select(Invoice).where(
                    Invoice.client_lot_id == cl.id,
                    Invoice.installment_number > cycle_start,
                    Invoice.installment_number <= cycle_end,
                    Invoice.status != InvoiceStatus.CANCELLED,
                )
            )
            cycle_invoices = list(cycle_rows.scalars().all())
            if not cycle_invoices:
                continue

            last_due = max(inv.due_date for inv in cycle_invoices)

            # The contract ends with this cycle: nothing left to renew, but the
            # deed still has to be drawn up once it is settled.
            highest = (await db.execute(
                select(func.max(Invoice.installment_number)).where(
                    Invoice.client_lot_id == cl.id
                )
            )).scalar() or 0
            if highest >= total:
                liquidated_ids = await get_boleto_liquidated_invoice_ids(db, cl.id)
                all_rows = await db.execute(
                    select(Invoice).where(
                        Invoice.client_lot_id == cl.id,
                        Invoice.status != InvoiceStatus.CANCELLED,
                    )
                )
                all_invoices = list(all_rows.scalars().all())
                fully_settled = all_invoices and all(
                    inv.status == InvoiceStatus.PAID and inv.id in liquidated_ids
                    for inv in all_invoices
                )
                if fully_settled and cl.status != ClientLotStatus.COMPLETED:
                    cl.status = ClientLotStatus.COMPLETED
                    completed += 1
                    await _ensure_deed_checklist(db, cl)
                    await _alert_escrituracao(db, cl, reason="contrato quitado")
                continue

            # Lead time: raise the renewal before the cycle's last due date.
            if today < last_due - timedelta(days=CYCLE_LEAD_DAYS):
                continue

            next_cycle = cl.current_cycle + 1
            existing = await db.execute(
                select(CycleApproval).where(
                    CycleApproval.client_lot_id == cl.id,
                    CycleApproval.cycle_number == next_cycle,
                )
            )
            if existing.scalar_one_or_none():
                continue

            # Settlement snapshot: only boleto-liquidated installments count.
            liquidated_ids = await get_boleto_liquidated_invoice_ids(db, cl.id)
            unpaid = [
                inv for inv in cycle_invoices
                if inv.status != InvoiceStatus.PAID or inv.id not in liquidated_ids
            ]
            overdue_amount = sum(
                (inv.amount for inv in unpaid if inv.due_date < today),
                Decimal("0"),
            )

            remaining_after = total - highest
            is_final = 0 < remaining_after <= cycle_size

            approval = CycleApproval(
                company_id=cl.company_id,
                client_lot_id=cl.id,
                cycle_number=next_cycle,
                status=CycleApprovalStatus.PENDING,
                previous_installment_value=cl.current_installment_value
                or (cl.total_value / total),
                unpaid_count=len(unpaid),
                overdue_amount=overdue_amount,
                is_final_cycle=is_final,
            )
            db.add(approval)
            created += 1

            if is_final:
                await _ensure_deed_checklist(db, cl)

            settled = len(cycle_invoices) - len(unpaid)
            alert_msg = (
                f"O ciclo {cl.current_cycle} do contrato (lote ID: {cl.id}) vence em "
                f"{last_due.strftime('%d/%m/%Y')}. Uma solicitação de aprovação para o "
                f"ciclo {next_cycle} foi criada. "
                f"Quitação: {settled} de {len(cycle_invoices)} parcelas liquidadas"
                + (f", {len(unpaid)} em aberto." if unpaid else ".")
                + f" Valor atual da parcela: R${cl.current_installment_value}."
            )
            if is_final:
                alert_msg += (
                    " ATENÇÃO: este é o último ciclo do contrato — inicie a escrituração."
                )

            try:
                await send_admin_alert(
                    company_id=str(cl.company_id),
                    subject=(
                        f"Ciclo {next_cycle} aguardando aprovação"
                        + (" — ÚLTIMO CICLO" if is_final else "")
                    ),
                    message=alert_msg,
                    db=db,
                )
            except Exception as exc:
                logger.warning("cycle_email_alert_failed", cl_id=str(cl.id), error=str(exc))
            try:
                await notify_admins(
                    db,
                    cl.company_id,
                    "notify_admin_cycle_request",
                    title=(
                        f"Ciclo {next_cycle} aguardando aprovação"
                        + (" — ÚLTIMO CICLO" if is_final else "")
                    ),
                    message=alert_msg,
                    n_type=NotificationType.CICLO_PENDENTE,
                    data={
                        "client_lot_id": str(cl.id),
                        "cycle_number": next_cycle,
                        "unpaid_count": len(unpaid),
                        "is_final_cycle": is_final,
                    },
                    staff_permission="manage_financial",
                )
            except Exception as exc:
                logger.warning("cycle_completion_alert_failed", cl_id=str(cl.id), error=str(exc))

        await db.commit()
        logger.info(
            "cycle_completion_check",
            approvals_created=created,
            contracts_completed=completed,
        )


async def _ensure_deed_checklist(db, client_lot) -> None:
    """Create the escrituração checklist for a contract, once."""
    from sqlalchemy import select
    from app.models.deed_checklist import DeedChecklist, default_items

    existing = await db.execute(
        select(DeedChecklist).where(DeedChecklist.client_lot_id == client_lot.id)
    )
    if existing.scalar_one_or_none():
        return
    db.add(
        DeedChecklist(
            company_id=client_lot.company_id,
            client_lot_id=client_lot.id,
            items=default_items(),
        )
    )


async def _alert_escrituracao(db, client_lot, *, reason: str) -> None:
    """Tell the admins a contract is ready for deed transfer."""
    from app.models.enums import NotificationType
    from app.services.admin_notify_service import notify_admins

    try:
        await notify_admins(
            db,
            client_lot.company_id,
            "notify_admin_cycle_request",
            title="Escrituração pendente",
            message=(
                f"O contrato (lote ID: {client_lot.id}) chegou ao fim ({reason}). "
                "Inicie a escrituração: o checklist de documentos já está disponível."
            ),
            n_type=NotificationType.ESCRITURACAO_PENDENTE,
            data={"client_lot_id": str(client_lot.id), "action": "deed_checklist"},
            staff_permission="manage_financial",
        )
    except Exception as exc:
        logger.warning(
            "escrituracao_alert_failed", cl_id=str(client_lot.id), error=str(exc)
        )


@celery.task(bind=True, max_retries=3, default_retry_delay=300)
def check_cycle_completions(self):
    """Daily task: check for completed 12-installment cycles and create approval requests."""
    try:
        run_in_task_loop(_notify_cycle_completion_async)
    except Exception as exc:
        logger.error("cycle_completion_check_failed", error=str(exc))
        self.retry(exc=exc)
