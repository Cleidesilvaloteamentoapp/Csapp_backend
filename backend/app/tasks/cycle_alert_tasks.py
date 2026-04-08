"""Celery tasks for cycle renewal alerts and batch generation."""

import asyncio
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.client_lot import ClientLot
from app.models.enums import ClientLotStatus, NotificationType
from app.models.invoice import Invoice
from app.models.user import Profile
from app.services.client_lot_service import get_remaining_installments, should_generate_next_batch
from app.services.notification_service import create_notification
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


async def _check_cycle_alerts_async(days_before: int = 30):
    """Check for client lots that need new batch generation.

    This task runs periodically to identify clients whose current 12-installment
    cycle is complete and are approaching the time to generate the next batch.

    Args:
        days_before: Days before next due date to trigger alert
    """
    from app.core.database import async_session_factory

    async with async_session_factory() as db:
        # Get all active client lots
        stmt = select(ClientLot).where(ClientLot.status == ClientLotStatus.ACTIVE)
        result = await db.execute(stmt)
        client_lots = result.scalars().all()

        alerts_created = 0

        for cl in client_lots:
            try:
                # Check if should generate next batch
                should_gen, reason = await should_generate_next_batch(
                    db, cl.id, days_before
                )

                if not should_gen:
                    continue

                # Get installment info
                info = await get_remaining_installments(db, cl.id)
                if not info:
                    continue

                # Get client and admin info
                client_stmt = select(Client).where(Client.id == cl.client_id)
                client_result = await db.execute(client_stmt)
                client = client_result.scalar_one_or_none()

                if not client:
                    continue

                # Get company admin to notify
                admin_stmt = (
                    select(Profile)
                    .where(
                        Profile.company_id == cl.company_id,
                        Profile.role == "COMPANY_ADMIN",
                    )
                    .limit(1)
                )
                admin_result = await db.execute(admin_stmt)
                admin = admin_result.scalar_one_or_none()

                if not admin:
                    continue

                # Create notification for admin
                await create_notification(
                    db=db,
                    company_id=cl.company_id,
                    user_id=admin.id,
                    title=f"Ciclo {info.current_cycle} completo - {client.full_name or client.email}",
                    message=(
                        f"O cliente {client.full_name or client.email} completou o "
                        f"{info.current_cycle}° ciclo de 12 parcelas. "
                        f"Restam {info.remaining_installments} parcelas. "
                        f"Clique para gerar o {info.next_cycle_number}° lote com reajuste."
                    ),
                    notification_type=NotificationType.CICLO_PENDENTE,
                    data={
                        "client_lot_id": str(cl.id),
                        "client_id": str(client.id),
                        "current_cycle": info.current_cycle,
                        "next_cycle": info.next_cycle_number,
                        "remaining_installments": info.remaining_installments,
                        "action": "generate_next_batch",
                    },
                )

                await db.commit()
                alerts_created += 1

                logger.info(
                    "cycle_alert_created",
                    client_lot_id=str(cl.id),
                    client_id=str(client.id),
                    cycle=info.current_cycle,
                )

            except Exception as exc:
                logger.error(
                    "cycle_alert_error",
                    client_lot_id=str(cl.id),
                    error=str(exc),
                )
                continue

        logger.info("cycle_alerts_completed", alerts_created=alerts_created)


@celery.task(bind=True, max_retries=3, default_retry_delay=300)
def check_cycle_alerts(self, days_before: int = 30):
    """Daily task: check for cycle renewal alerts.

    Run this task daily to identify clients whose cycle is complete
    and notify admins to generate the next batch.

    Args:
        days_before: Days before next due date to trigger alert
    """
    try:
        _run_async(_check_cycle_alerts_async(days_before))
    except Exception as exc:
        logger.error("check_cycle_alerts_failed", error=str(exc))
        self.retry(exc=exc)


async def _generate_next_batch_for_client_async(
    client_lot_id: str,
    adjustment_rate: float,
    admin_id: str,
):
    """Generate next batch of 12 installments for a client lot.

    Args:
        client_lot_id: Client lot UUID
        adjustment_rate: Adjustment rate as decimal (e.g., 0.05 for 5%)
        admin_id: Admin profile UUID who triggered the generation
    """
    from app.core.database import async_session_factory
    from decimal import Decimal

    async with async_session_factory() as db:
        cl_id = UUID(client_lot_id)

        # Get client lot
        stmt = select(ClientLot).where(ClientLot.id == cl_id)
        result = await db.execute(stmt)
        client_lot = result.scalar_one_or_none()

        if not client_lot:
            logger.error("client_lot_not_found", client_lot_id=client_lot_id)
            return

        # Check if ready for next batch
        should_gen, reason = await should_generate_next_batch(db, cl_id)
        if not should_gen:
            logger.warning("not_ready_for_batch", client_lot_id=client_lot_id, reason=reason)
            return

        # Get client info
        client_stmt = select(Client).where(Client.id == client_lot.client_id)
        client_result = await db.execute(client_stmt)
        client = client_result.scalar_one_or_none()

        # Get last invoice to determine next due date
        last_inv_stmt = (
            select(Invoice)
            .where(
                Invoice.client_lot_id == cl_id,
                Invoice.status != "CANCELLED",
            )
            .order_by(Invoice.due_date.desc())
            .limit(1)
        )
        last_result = await db.execute(last_inv_stmt)
        last_invoice = last_result.scalar_one_or_none()

        next_due_date = (last_invoice.due_date + timedelta(days=30)) if last_invoice else date.today() + timedelta(days=30)

        # Calculate new value with adjustment
        current_value = client_lot.current_installment_value
        if not current_value:
            total_installments = client_lot.total_installments or 1
            current_value = client_lot.total_value / total_installments

        new_value = float(current_value * (1 + Decimal(str(adjustment_rate))))

        # Update client lot
        client_lot.current_cycle += 1
        client_lot.current_installment_value = Decimal(str(new_value))
        client_lot.last_adjustment_date = date.today()

        await db.commit()

        logger.info(
            "next_batch_prepared",
            client_lot_id=client_lot_id,
            new_cycle=client_lot.current_cycle,
            new_value=new_value,
            next_due_date=str(next_due_date),
        )

        # Note: The actual batch creation would be triggered via the existing
        # batch creation endpoint. This task prepares the client lot for it.


@celery.task(bind=True, max_retries=2)
def generate_next_batch_for_client(
    self,
    client_lot_id: str,
    adjustment_rate: float,
    admin_id: str,
):
    """Generate next batch of 12 installments for a client lot.

    This is a wrapper that prepares the client lot for batch creation.

    Args:
        client_lot_id: Client lot UUID
        adjustment_rate: Adjustment rate as decimal
        admin_id: Admin profile UUID who triggered
    """
    try:
        _run_async(
            _generate_next_batch_for_client_async(
                client_lot_id, adjustment_rate, admin_id
            )
        )
    except Exception as exc:
        logger.error("generate_next_batch_failed", error=str(exc))
        self.retry(exc=exc)
