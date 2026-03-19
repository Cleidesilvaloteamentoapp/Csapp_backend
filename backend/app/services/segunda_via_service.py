
"""Service for issuing second copy boletos with automatic penalty/interest calculation."""

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.boleto import Boleto
from app.models.client import Client
from app.models.enums import BoletoStatus, ContractEventType, InvoiceStatus
from app.models.invoice import Invoice
from app.services.contract_history_service import record_event
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Default penalty and interest rates
PENALTY_RATE = Decimal("0.02")        # 2% multa
DAILY_INTEREST_RATE = Decimal("0.00033")  # ~1% ao mês (0.033%/dia)


def calculate_correction(
    original_amount: Decimal,
    due_date: date,
    calculation_date: Optional[date] = None,
    *,
    penalty_rate: Optional[Decimal] = None,
    daily_interest_rate: Optional[Decimal] = None,
) -> dict:
    """Calculate penalty + interest for an overdue amount.

    Uses per-lot rates if provided, otherwise falls back to system defaults.

    Returns a dict with:
      - original_amount
      - penalty (default 2% flat)
      - interest (default 0.033%/day * days overdue)
      - corrected_amount
      - days_overdue
      - penalty_rate_used
      - interest_rate_used
    """
    calc_date = calculation_date or date.today()
    days_overdue = max(0, (calc_date - due_date).days)

    p_rate = penalty_rate if penalty_rate is not None else PENALTY_RATE
    i_rate = daily_interest_rate if daily_interest_rate is not None else DAILY_INTEREST_RATE

    if days_overdue == 0:
        return {
            "original_amount": original_amount,
            "penalty": Decimal("0"),
            "interest": Decimal("0"),
            "corrected_amount": original_amount,
            "days_overdue": 0,
            "penalty_rate_used": p_rate,
            "interest_rate_used": i_rate,
        }

    penalty = (original_amount * p_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    interest = (original_amount * i_rate * days_overdue).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    corrected_amount = original_amount + penalty + interest

    return {
        "original_amount": original_amount,
        "penalty": penalty,
        "interest": interest,
        "corrected_amount": corrected_amount,
        "days_overdue": days_overdue,
        "penalty_rate_used": p_rate,
        "interest_rate_used": i_rate,
    }


async def preview_segunda_via(
    db: AsyncSession,
    company_id: UUID,
    invoice_id: UUID,
) -> dict:
    """Preview the corrected amount for an overdue invoice without creating a new boleto."""
    row = await db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.company_id == company_id,
        )
    )
    invoice = row.scalar_one_or_none()
    if not invoice:
        raise ValueError("Invoice not found")

    if invoice.status not in (InvoiceStatus.OVERDUE, InvoiceStatus.PENDING):
        raise ValueError(f"Invoice is in status {invoice.status.value}, cannot issue second copy")

    # Load per-lot rates if available
    from app.models.client_lot import ClientLot
    cl_row = await db.execute(
        select(ClientLot).where(ClientLot.id == invoice.client_lot_id)
    )
    client_lot = cl_row.scalar_one_or_none()

    correction = calculate_correction(
        invoice.amount,
        invoice.due_date,
        penalty_rate=client_lot.penalty_rate if client_lot else None,
        daily_interest_rate=client_lot.daily_interest_rate if client_lot else None,
    )
    new_due_date = date.today() + timedelta(days=3)

    return {
        "invoice_id": str(invoice.id),
        "installment_number": invoice.installment_number,
        **correction,
        "new_due_date": new_due_date,
    }


async def issue_segunda_via(
    db: AsyncSession,
    company_id: UUID,
    invoice_id: UUID,
    *,
    performed_by: Optional[UUID] = None,
    ip_address: Optional[str] = None,
    new_due_date: Optional[date] = None,
) -> dict:
    """Issue a second copy for an overdue invoice.

    This creates a record in contract_history and returns the corrected values.
    The actual Sicredi boleto creation should be done by the caller using
    the returned corrected amount and new due date.
    """
    row = await db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.company_id == company_id,
        )
    )
    invoice = row.scalar_one_or_none()
    if not invoice:
        raise ValueError("Invoice not found")

    if invoice.status not in (InvoiceStatus.OVERDUE, InvoiceStatus.PENDING):
        raise ValueError(f"Invoice is in status {invoice.status.value}, cannot issue second copy")

    # Get client_id from client_lot
    from app.models.client_lot import ClientLot
    cl_row = await db.execute(
        select(ClientLot).where(ClientLot.id == invoice.client_lot_id)
    )
    client_lot = cl_row.scalar_one_or_none()
    if not client_lot:
        raise ValueError("Client lot not found for this invoice")

    correction = calculate_correction(
        invoice.amount,
        invoice.due_date,
        penalty_rate=client_lot.penalty_rate,
        daily_interest_rate=client_lot.daily_interest_rate,
    )
    due = new_due_date or (date.today() + timedelta(days=3))

    await record_event(
        db,
        company_id=company_id,
        client_id=client_lot.client_id,
        client_lot_id=client_lot.id,
        invoice_id=invoice.id,
        event_type=ContractEventType.SECOND_COPY,
        description=(
            f"Segunda via emitida para parcela #{invoice.installment_number}. "
            f"Valor original: R${correction['original_amount']}, "
            f"Multa: R${correction['penalty']}, "
            f"Juros: R${correction['interest']}, "
            f"Valor corrigido: R${correction['corrected_amount']}"
        ),
        amount=correction["corrected_amount"],
        previous_value=str(correction["original_amount"]),
        new_value=str(correction["corrected_amount"]),
        metadata_json={
            "days_overdue": correction["days_overdue"],
            "penalty": str(correction["penalty"]),
            "interest": str(correction["interest"]),
            "new_due_date": due.isoformat(),
        },
        performed_by=performed_by,
        ip_address=ip_address,
    )

    logger.info(
        "segunda_via_issued",
        invoice_id=str(invoice_id),
        corrected_amount=str(correction["corrected_amount"]),
    )

    return {
        "invoice_id": str(invoice.id),
        "client_id": str(client_lot.client_id),
        "client_lot_id": str(client_lot.id),
        "installment_number": invoice.installment_number,
        **correction,
        "new_due_date": due,
    }
