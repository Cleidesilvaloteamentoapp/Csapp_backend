
"""Service for contract rescission (distrato) workflows."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.client_lot import ClientLot
from app.models.enums import (
    ClientLotStatus,
    ClientStatus,
    ContractEventType,
    InvoiceStatus,
    LotStatus,
    RescissionStatus,
)
from app.models.invoice import Invoice
from app.models.lot import Lot
from app.models.rescission import Rescission
from app.services.contract_history_service import record_event
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def create_rescission(
    db: AsyncSession,
    company_id: UUID,
    admin_id: UUID,
    *,
    client_id: UUID,
    client_lot_id: UUID,
    reason: str,
    admin_notes: Optional[str] = None,
) -> Rescission:
    """Create a rescission request for a client contract."""
    # Get client_lot
    cl_row = await db.execute(
        select(ClientLot).where(
            ClientLot.id == client_lot_id,
            ClientLot.company_id == company_id,
            ClientLot.client_id == client_id,
        )
    )
    client_lot = cl_row.scalar_one_or_none()
    if not client_lot:
        raise ValueError("Client lot not found")

    if client_lot.status in (ClientLotStatus.CANCELLED, ClientLotStatus.RESCINDED):
        raise ValueError(f"Client lot already in status {client_lot.status.value}")

    # Calculate paid and debt amounts
    inv_rows = await db.execute(
        select(Invoice).where(Invoice.client_lot_id == client_lot_id)
    )
    invoices = list(inv_rows.scalars().all())

    total_paid = sum(inv.amount for inv in invoices if inv.status == InvoiceStatus.PAID)
    total_debt = sum(inv.amount for inv in invoices if inv.status in (InvoiceStatus.PENDING, InvoiceStatus.OVERDUE))

    rescission = Rescission(
        company_id=company_id,
        client_id=client_id,
        client_lot_id=client_lot_id,
        status=RescissionStatus.REQUESTED,
        reason=reason,
        total_paid=total_paid,
        total_debt=total_debt,
        refund_amount=Decimal("0"),
        penalty_amount=Decimal("0"),
        request_date=date.today(),
        admin_notes=admin_notes,
        requested_by=admin_id,
    )
    db.add(rescission)
    await db.flush()

    await record_event(
        db,
        company_id=company_id,
        client_id=client_id,
        client_lot_id=client_lot_id,
        event_type=ContractEventType.RESCISSION_STARTED,
        description=f"Processo de rescisão iniciado. Motivo: {reason}",
        amount=total_debt,
        performed_by=admin_id,
    )

    logger.info("rescission_created", rescission_id=str(rescission.id), client_id=str(client_id))
    return rescission


async def approve_rescission(
    db: AsyncSession,
    company_id: UUID,
    admin_id: UUID,
    rescission_id: UUID,
    *,
    approved: bool,
    refund_amount: Decimal = Decimal("0"),
    penalty_amount: Decimal = Decimal("0"),
    admin_notes: Optional[str] = None,
) -> Rescission:
    """Approve or reject a rescission request."""
    row = await db.execute(
        select(Rescission).where(
            Rescission.id == rescission_id,
            Rescission.company_id == company_id,
        )
    )
    rescission = row.scalar_one_or_none()
    if not rescission:
        raise ValueError("Rescission not found")

    if rescission.status not in (RescissionStatus.REQUESTED, RescissionStatus.PENDING_APPROVAL):
        raise ValueError(f"Cannot approve rescission in status {rescission.status.value}")

    if approved:
        rescission.status = RescissionStatus.APPROVED
        rescission.refund_amount = refund_amount
        rescission.penalty_amount = penalty_amount
    else:
        rescission.status = RescissionStatus.CANCELLED

    rescission.approved_by = admin_id
    rescission.approval_date = date.today()
    if admin_notes:
        rescission.admin_notes = admin_notes

    await db.flush()
    return rescission


async def complete_rescission(
    db: AsyncSession,
    company_id: UUID,
    admin_id: UUID,
    rescission_id: UUID,
) -> Rescission:
    """Complete an approved rescission: cancel invoices, release lot."""
    row = await db.execute(
        select(Rescission).where(
            Rescission.id == rescission_id,
            Rescission.company_id == company_id,
        )
    )
    rescission = row.scalar_one_or_none()
    if not rescission:
        raise ValueError("Rescission not found")

    if rescission.status != RescissionStatus.APPROVED:
        raise ValueError("Rescission must be APPROVED before completing")

    # 1. Cancel all pending/overdue invoices
    inv_rows = await db.execute(
        select(Invoice).where(
            Invoice.client_lot_id == rescission.client_lot_id,
            Invoice.status.in_([InvoiceStatus.PENDING, InvoiceStatus.OVERDUE]),
        )
    )
    for inv in inv_rows.scalars().all():
        inv.status = InvoiceStatus.CANCELLED

    # 2. Update client_lot status to RESCINDED
    cl_row = await db.execute(
        select(ClientLot).where(ClientLot.id == rescission.client_lot_id)
    )
    client_lot = cl_row.scalar_one_or_none()
    if client_lot:
        client_lot.status = ClientLotStatus.RESCINDED

        # 3. Return lot to AVAILABLE status
        lot_row = await db.execute(
            select(Lot).where(Lot.id == client_lot.lot_id)
        )
        lot = lot_row.scalar_one_or_none()
        if lot and lot.status == LotStatus.SOLD:
            lot.status = LotStatus.AVAILABLE

    # 4. Update client status
    client_row = await db.execute(
        select(Client).where(Client.id == rescission.client_id)
    )
    client = client_row.scalar_one_or_none()
    if client:
        # Check if client has other active lots
        other_lots = await db.execute(
            select(func.count(ClientLot.id)).where(
                ClientLot.client_id == client.id,
                ClientLot.status == ClientLotStatus.ACTIVE,
                ClientLot.id != rescission.client_lot_id,
            )
        )
        if (other_lots.scalar() or 0) == 0:
            client.status = ClientStatus.RESCINDED

    # 5. Finalize rescission
    rescission.status = RescissionStatus.COMPLETED
    rescission.completion_date = date.today()

    await record_event(
        db,
        company_id=company_id,
        client_id=rescission.client_id,
        client_lot_id=rescission.client_lot_id,
        event_type=ContractEventType.RESCISSION_COMPLETED,
        description="Rescisão concluída. Lote devolvido ao estoque.",
        amount=rescission.refund_amount,
        performed_by=admin_id,
    )

    await db.flush()
    logger.info("rescission_completed", rescission_id=str(rescission_id))
    return rescission
