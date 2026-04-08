"""ClientLot service for managing client-lot relationships and installment tracking."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client_lot import ClientLot
from app.models.enums import ClientLotStatus, InvoiceStatus
from app.models.invoice import Invoice
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class InstallmentInfo:
    """Information about installments for a client lot."""

    total_installments: int
    paid_installments: int
    remaining_installments: int
    current_cycle: int
    next_cycle_number: int
    installments_in_current_cycle: int
    is_legacy_client: bool


async def get_remaining_installments(
    db: AsyncSession, client_lot_id: UUID
) -> Optional[InstallmentInfo]:
    """Calculate remaining installments for a client lot.

    For legacy clients (paid_installments > 0): uses the manual count.
    For new clients: counts invoices with PAID status.

    Args:
        db: Database session
        client_lot_id: Client lot UUID

    Returns:
        InstallmentInfo with breakdown or None if client lot not found
    """
    stmt = select(ClientLot).where(ClientLot.id == client_lot_id)
    result = await db.execute(stmt)
    client_lot = result.scalar_one_or_none()

    if not client_lot:
        return None

    total_installments = client_lot.total_installments or 1
    current_cycle = client_lot.current_cycle or 1

    # Check if legacy client (has manual paid_installments count)
    is_legacy = client_lot.paid_installments is not None and client_lot.paid_installments > 0

    if is_legacy:
        # Use manual count for legacy clients
        paid = client_lot.paid_installments or 0
    else:
        # Count paid invoices for new clients
        paid_count_stmt = (
            select(func.count(Invoice.id))
            .where(
                Invoice.client_lot_id == client_lot_id,
                Invoice.status == InvoiceStatus.PAID,
            )
        )
        paid_result = await db.execute(paid_count_stmt)
        paid = paid_result.scalar() or 0

    remaining = max(0, total_installments - paid)

    # Calculate cycle info
    cycle_size = 12
    next_cycle_number = current_cycle + 1

    # Count installments in current cycle
    current_cycle_start = (current_cycle - 1) * cycle_size
    current_cycle_end = current_cycle * cycle_size

    if is_legacy:
        installments_in_current_cycle = min(paid - current_cycle_start, cycle_size)
        installments_in_current_cycle = max(0, installments_in_current_cycle)
    else:
        cycle_invoices_stmt = (
            select(func.count(Invoice.id))
            .where(
                Invoice.client_lot_id == client_lot_id,
                Invoice.installment_number > current_cycle_start,
                Invoice.installment_number <= current_cycle_end,
                Invoice.status == InvoiceStatus.PAID,
            )
        )
        cycle_result = await db.execute(cycle_invoices_stmt)
        installments_in_current_cycle = cycle_result.scalar() or 0

    return InstallmentInfo(
        total_installments=total_installments,
        paid_installments=paid,
        remaining_installments=remaining,
        current_cycle=current_cycle,
        next_cycle_number=next_cycle_number,
        installments_in_current_cycle=installments_in_current_cycle,
        is_legacy_client=is_legacy,
    )


async def should_generate_next_batch(
    db: AsyncSession, client_lot_id: UUID, days_threshold: int = 30
) -> tuple[bool, Optional[str]]:
    """Check if it's time to generate the next batch of 12 installments.

    Args:
        db: Database session
        client_lot_id: Client lot UUID
        days_threshold: Days before next due date to trigger alert

    Returns:
        Tuple of (should_generate, reason)
    """
    info = await get_remaining_installments(db, client_lot_id)
    if not info:
        return False, "Client lot not found"

    # Check if current cycle is complete (12 paid)
    if info.installments_in_current_cycle < 12:
        return False, f"Current cycle not complete ({info.installments_in_current_cycle}/12 paid)"

    # Check if there are remaining installments
    if info.remaining_installments <= 0:
        return False, "All installments already paid"

    # Check if next batch would exceed total
    if info.remaining_installments < 12:
        return False, f"Only {info.remaining_installments} installments remaining"

    # Check if there's a recent invoice due date to compare against
    next_due_stmt = (
        select(Invoice)
        .where(
            Invoice.client_lot_id == client_lot_id,
            Invoice.status == InvoiceStatus.PENDING,
        )
        .order_by(Invoice.due_date.asc())
        .limit(1)
    )
    next_result = await db.execute(next_due_stmt)
    next_invoice = next_result.scalar_one_or_none()

    if next_invoice:
        from datetime import date, timedelta

        days_until_due = (next_invoice.due_date - date.today()).days
        if days_until_due > days_threshold:
            return False, f"Next due date is {days_until_due} days away (threshold: {days_threshold})"

    return True, f"Cycle {info.current_cycle} complete - ready for cycle {info.next_cycle_number}"


async def calculate_next_installment_value(
    db: AsyncSession, client_lot_id: UUID, adjustment_rate: Decimal
) -> Optional[Decimal]:
    """Calculate the next installment value with adjustment.

    Args:
        db: Database session
        client_lot_id: Client lot UUID
        adjustment_rate: Adjustment rate as decimal (e.g., 0.05 for 5%)

    Returns:
        New installment value or None if client lot not found
    """
    stmt = select(ClientLot).where(ClientLot.id == client_lot_id)
    result = await db.execute(stmt)
    client_lot = result.scalar_one_or_none()

    if not client_lot:
        return None

    # Get current value (from last invoice or current_installment_value)
    current_value = client_lot.current_installment_value

    if not current_value:
        # Calculate from total value
        total_installments = client_lot.total_installments or 1
        current_value = client_lot.total_value / total_installments

    # Apply adjustment
    new_value = current_value * (1 + adjustment_rate)

    return new_value.quantize(Decimal("0.01"))
