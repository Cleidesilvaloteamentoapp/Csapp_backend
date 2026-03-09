
"""Service for recording contract history events."""

from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract_history import ContractHistory
from app.models.enums import ContractEventType


async def record_event(
    db: AsyncSession,
    *,
    company_id: UUID,
    client_id: UUID,
    event_type: ContractEventType,
    description: str,
    client_lot_id: Optional[UUID] = None,
    invoice_id: Optional[UUID] = None,
    boleto_id: Optional[UUID] = None,
    amount: Optional[Decimal] = None,
    previous_value: Optional[str] = None,
    new_value: Optional[str] = None,
    metadata_json: Optional[dict] = None,
    performed_by: Optional[UUID] = None,
    ip_address: Optional[str] = None,
) -> ContractHistory:
    """Create an immutable contract history record."""
    entry = ContractHistory(
        company_id=company_id,
        client_id=client_id,
        client_lot_id=client_lot_id,
        invoice_id=invoice_id,
        boleto_id=boleto_id,
        event_type=event_type,
        description=description,
        amount=amount,
        previous_value=previous_value,
        new_value=new_value,
        metadata_json=metadata_json or {},
        performed_by=performed_by,
        ip_address=ip_address,
    )
    db.add(entry)
    await db.flush()
    return entry


async def get_client_history(
    db: AsyncSession,
    company_id: UUID,
    client_id: UUID,
    *,
    client_lot_id: Optional[UUID] = None,
    event_type: Optional[ContractEventType] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[ContractHistory]:
    """Retrieve contract history for a client with optional filters."""
    stmt = (
        select(ContractHistory)
        .where(
            ContractHistory.company_id == company_id,
            ContractHistory.client_id == client_id,
        )
    )
    if client_lot_id:
        stmt = stmt.where(ContractHistory.client_lot_id == client_lot_id)
    if event_type:
        stmt = stmt.where(ContractHistory.event_type == event_type)

    stmt = stmt.order_by(ContractHistory.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())
