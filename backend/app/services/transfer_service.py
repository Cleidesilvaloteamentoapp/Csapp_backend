
"""Service for contract/lot ownership transfers between clients."""

from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.boleto import Boleto
from app.models.client import Client
from app.models.client_lot import ClientLot
from app.models.contract_transfer import ContractTransfer
from app.models.enums import (
    BoletoStatus,
    ClientLotStatus,
    ContractEventType,
    InvoiceStatus,
    TransferStatus,
)
from app.models.invoice import Invoice
from app.services.contract_history_service import record_event
from app.utils.exceptions import ResourceNotFoundError
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def _validate_transfer(
    db: AsyncSession,
    company_id: UUID,
    client_lot_id: UUID,
    from_client_id: UUID,
    to_client_id: UUID,
) -> tuple[ClientLot, Client, Client]:
    """Validate all entities exist and belong to the same company."""
    cl = await db.execute(
        select(ClientLot).where(
            ClientLot.id == client_lot_id,
            ClientLot.company_id == company_id,
            ClientLot.status == ClientLotStatus.ACTIVE,
        )
    )
    client_lot = cl.scalar_one_or_none()
    if not client_lot:
        raise ResourceNotFoundError("Active ClientLot")

    if client_lot.client_id != from_client_id:
        raise ValueError("from_client_id does not match current lot owner")

    fc = await db.execute(
        select(Client).where(Client.id == from_client_id, Client.company_id == company_id)
    )
    from_client = fc.scalar_one_or_none()
    if not from_client:
        raise ResourceNotFoundError("Source Client")

    tc = await db.execute(
        select(Client).where(Client.id == to_client_id, Client.company_id == company_id)
    )
    to_client = tc.scalar_one_or_none()
    if not to_client:
        raise ResourceNotFoundError("Target Client")

    if from_client_id == to_client_id:
        raise ValueError("Cannot transfer to the same client")

    return client_lot, from_client, to_client


async def create_transfer(
    db: AsyncSession,
    company_id: UUID,
    requested_by: UUID,
    *,
    client_lot_id: UUID,
    from_client_id: UUID,
    to_client_id: UUID,
    transfer_fee: Optional[float] = None,
    reason: Optional[str] = None,
) -> ContractTransfer:
    """Create a pending transfer request."""
    await _validate_transfer(db, company_id, client_lot_id, from_client_id, to_client_id)

    transfer = ContractTransfer(
        company_id=company_id,
        client_lot_id=client_lot_id,
        from_client_id=from_client_id,
        to_client_id=to_client_id,
        transfer_fee=transfer_fee or 0,
        reason=reason,
        status=TransferStatus.PENDING,
        requested_by=requested_by,
    )
    db.add(transfer)
    await db.flush()
    logger.info("transfer_created", transfer_id=str(transfer.id))
    return transfer


async def approve_transfer(
    db: AsyncSession,
    company_id: UUID,
    transfer_id: UUID,
    approved_by: UUID,
    *,
    admin_notes: Optional[str] = None,
    transfer_date: Optional[date] = None,
) -> ContractTransfer:
    """Approve a pending transfer (SUPER_ADMIN only)."""
    row = await db.execute(
        select(ContractTransfer).where(
            ContractTransfer.id == transfer_id,
            ContractTransfer.company_id == company_id,
            ContractTransfer.status == TransferStatus.PENDING,
        )
    )
    transfer = row.scalar_one_or_none()
    if not transfer:
        raise ResourceNotFoundError("Pending ContractTransfer")

    transfer.status = TransferStatus.APPROVED
    transfer.approved_by = approved_by
    transfer.approved_at = datetime.now(timezone.utc)
    transfer.admin_notes = admin_notes
    transfer.transfer_date = transfer_date or date.today()
    await db.flush()
    logger.info("transfer_approved", transfer_id=str(transfer_id))
    return transfer


async def complete_transfer(
    db: AsyncSession,
    company_id: UUID,
    transfer_id: UUID,
    performed_by: UUID,
    *,
    admin_notes: Optional[str] = None,
) -> ContractTransfer:
    """Complete an approved transfer: migrate lot, invoices, and boletos to new client."""
    row = await db.execute(
        select(ContractTransfer).where(
            ContractTransfer.id == transfer_id,
            ContractTransfer.company_id == company_id,
            ContractTransfer.status == TransferStatus.APPROVED,
        )
    )
    transfer = row.scalar_one_or_none()
    if not transfer:
        raise ResourceNotFoundError("Approved ContractTransfer")

    # 1. Update client_lot ownership
    cl_row = await db.execute(
        select(ClientLot).where(ClientLot.id == transfer.client_lot_id)
    )
    client_lot = cl_row.scalar_one()
    client_lot.previous_client_id = transfer.from_client_id
    client_lot.client_id = transfer.to_client_id
    client_lot.transfer_date = transfer.transfer_date or date.today()

    # 2. Migrate pending invoices to new client (via client_lot, already linked)
    # Invoices are linked to client_lot, not directly to client, so they follow automatically.

    # 3. Migrate pending boletos to new client
    await db.execute(
        update(Boleto)
        .where(
            Boleto.client_id == transfer.from_client_id,
            Boleto.company_id == company_id,
            Boleto.status.in_([BoletoStatus.NORMAL, BoletoStatus.VENCIDO]),
        )
        .values(client_id=transfer.to_client_id)
    )

    # 4. Mark transfer as completed
    transfer.status = TransferStatus.COMPLETED
    transfer.completed_at = datetime.now(timezone.utc)
    if admin_notes:
        transfer.admin_notes = (transfer.admin_notes or "") + f"\n{admin_notes}"

    # 5. Record in contract history
    await record_event(
        db,
        company_id=company_id,
        client_id=transfer.to_client_id,
        client_lot_id=transfer.client_lot_id,
        event_type=ContractEventType.TRANSFER,
        description=(
            f"Transferência de titularidade concluída. "
            f"Antigo titular: {transfer.from_client_id}, "
            f"Novo titular: {transfer.to_client_id}"
        ),
        performed_by=performed_by,
        metadata_json={
            "transfer_id": str(transfer.id),
            "from_client_id": str(transfer.from_client_id),
            "to_client_id": str(transfer.to_client_id),
            "transfer_fee": str(transfer.transfer_fee) if transfer.transfer_fee else None,
        },
    )

    await db.flush()
    logger.info("transfer_completed", transfer_id=str(transfer_id))
    return transfer


async def cancel_transfer(
    db: AsyncSession,
    company_id: UUID,
    transfer_id: UUID,
    admin_notes: Optional[str] = None,
) -> ContractTransfer:
    """Cancel a pending or approved transfer."""
    row = await db.execute(
        select(ContractTransfer).where(
            ContractTransfer.id == transfer_id,
            ContractTransfer.company_id == company_id,
            ContractTransfer.status.in_([TransferStatus.PENDING, TransferStatus.APPROVED]),
        )
    )
    transfer = row.scalar_one_or_none()
    if not transfer:
        raise ResourceNotFoundError("ContractTransfer (pending or approved)")

    transfer.status = TransferStatus.CANCELLED
    if admin_notes:
        transfer.admin_notes = admin_notes
    await db.flush()
    logger.info("transfer_cancelled", transfer_id=str(transfer_id))
    return transfer
