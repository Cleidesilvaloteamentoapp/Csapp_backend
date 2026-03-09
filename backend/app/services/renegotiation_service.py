
"""Service for debt renegotiation workflows."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.client_lot import ClientLot
from app.models.enums import (
    ClientStatus,
    ContractEventType,
    InvoiceStatus,
    RenegotiationStatus,
)
from app.models.invoice import Invoice
from app.models.renegotiation import Renegotiation
from app.services.contract_history_service import record_event
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def calculate_debt(
    db: AsyncSession,
    company_id: UUID,
    client_id: UUID,
    client_lot_id: UUID,
) -> dict:
    """Calculate total overdue debt for a client_lot including penalties and interest."""
    overdue_rows = await db.execute(
        select(Invoice).where(
            Invoice.company_id == company_id,
            Invoice.client_lot_id == client_lot_id,
            Invoice.status == InvoiceStatus.OVERDUE,
        ).order_by(Invoice.due_date)
    )
    overdue_invoices = list(overdue_rows.scalars().all())

    today = date.today()
    total_principal = Decimal("0")
    total_penalty = Decimal("0")
    total_interest = Decimal("0")

    for inv in overdue_invoices:
        total_principal += inv.amount
        # Multa: 2% sobre o valor
        penalty = inv.amount * Decimal("0.02")
        total_penalty += penalty
        # Juros: 1% ao mês (0.033%/dia)
        days_overdue = max(0, (today - inv.due_date).days)
        daily_interest = inv.amount * Decimal("0.00033")
        interest = daily_interest * days_overdue
        total_interest += interest

    return {
        "overdue_invoices": overdue_invoices,
        "overdue_count": len(overdue_invoices),
        "total_principal": total_principal,
        "total_penalty": round(total_penalty, 2),
        "total_interest": round(total_interest, 2),
        "total_debt": round(total_principal + total_penalty + total_interest, 2),
    }


async def create_renegotiation(
    db: AsyncSession,
    company_id: UUID,
    admin_id: UUID,
    *,
    client_id: UUID,
    client_lot_id: UUID,
    discount_amount: Decimal = Decimal("0"),
    penalty_waived: Decimal = Decimal("0"),
    interest_waived: Decimal = Decimal("0"),
    new_installments: int = 1,
    first_due_date: date,
    reason: Optional[str] = None,
    admin_notes: Optional[str] = None,
) -> Renegotiation:
    """Create a renegotiation proposal and calculate the final amount."""
    debt = await calculate_debt(db, company_id, client_id, client_lot_id)

    if debt["overdue_count"] == 0:
        raise ValueError("No overdue invoices found for this contract")

    # Calculate final amount after waivers and discounts
    effective_penalty = max(Decimal("0"), debt["total_penalty"] - penalty_waived)
    effective_interest = max(Decimal("0"), debt["total_interest"] - interest_waived)
    final_amount = max(
        Decimal("0"),
        debt["total_principal"] + effective_penalty + effective_interest - discount_amount
    )

    renego = Renegotiation(
        company_id=company_id,
        client_id=client_id,
        client_lot_id=client_lot_id,
        status=RenegotiationStatus.DRAFT,
        original_debt_amount=debt["total_debt"],
        overdue_invoices_count=debt["overdue_count"],
        penalty_amount=debt["total_penalty"],
        interest_amount=debt["total_interest"],
        discount_amount=discount_amount,
        penalty_waived=penalty_waived,
        interest_waived=interest_waived,
        final_amount=round(final_amount, 2),
        new_installments=new_installments,
        first_due_date=first_due_date,
        reason=reason,
        admin_notes=admin_notes,
        cancelled_invoice_ids=[str(inv.id) for inv in debt["overdue_invoices"]],
        created_by=admin_id,
    )
    db.add(renego)
    await db.flush()

    # Record in contract history
    await record_event(
        db,
        company_id=company_id,
        client_id=client_id,
        client_lot_id=client_lot_id,
        event_type=ContractEventType.RENEGOTIATION,
        description=f"Renegociação criada: dívida original R${debt['total_debt']}, valor final R${final_amount}",
        amount=final_amount,
        previous_value=str(debt["total_debt"]),
        new_value=str(final_amount),
        performed_by=admin_id,
    )

    logger.info("renegotiation_created", renego_id=str(renego.id), client_id=str(client_id))
    return renego


async def approve_renegotiation(
    db: AsyncSession,
    company_id: UUID,
    admin_id: UUID,
    renego_id: UUID,
    *,
    approved: bool,
    admin_notes: Optional[str] = None,
) -> Renegotiation:
    """Approve or reject a renegotiation proposal."""
    row = await db.execute(
        select(Renegotiation).where(
            Renegotiation.id == renego_id,
            Renegotiation.company_id == company_id,
        )
    )
    renego = row.scalar_one_or_none()
    if not renego:
        raise ValueError("Renegotiation not found")

    if renego.status not in (RenegotiationStatus.DRAFT, RenegotiationStatus.PENDING_APPROVAL):
        raise ValueError(f"Cannot approve renegotiation in status {renego.status.value}")

    now = datetime.now(timezone.utc)

    if approved:
        renego.status = RenegotiationStatus.APPROVED
        renego.approved_by = admin_id
        renego.approved_at = now
        if admin_notes:
            renego.admin_notes = admin_notes
    else:
        renego.status = RenegotiationStatus.REJECTED
        renego.approved_by = admin_id
        renego.approved_at = now
        if admin_notes:
            renego.admin_notes = admin_notes

    await db.flush()
    return renego


async def apply_renegotiation(
    db: AsyncSession,
    company_id: UUID,
    admin_id: UUID,
    renego_id: UUID,
) -> Renegotiation:
    """Apply an approved renegotiation: cancel old invoices, create new ones."""
    row = await db.execute(
        select(Renegotiation).where(
            Renegotiation.id == renego_id,
            Renegotiation.company_id == company_id,
        )
    )
    renego = row.scalar_one_or_none()
    if not renego:
        raise ValueError("Renegotiation not found")

    if renego.status != RenegotiationStatus.APPROVED:
        raise ValueError("Renegotiation must be APPROVED before applying")

    # 1. Cancel overdue invoices
    for inv_id_str in (renego.cancelled_invoice_ids or []):
        inv_row = await db.execute(
            select(Invoice).where(Invoice.id == inv_id_str)
        )
        inv = inv_row.scalar_one_or_none()
        if inv and inv.status == InvoiceStatus.OVERDUE:
            inv.status = InvoiceStatus.CANCELLED
            await record_event(
                db,
                company_id=company_id,
                client_id=renego.client_id,
                client_lot_id=renego.client_lot_id,
                invoice_id=inv.id,
                event_type=ContractEventType.BOLETO_CANCELLED,
                description=f"Invoice #{inv.installment_number} cancelada por renegociação",
                amount=inv.amount,
                performed_by=admin_id,
            )

    # 2. Create new invoices from renegotiated terms
    installment_value = round(renego.final_amount / renego.new_installments, 2)
    new_invoice_ids = []

    # Get existing invoice count for numbering
    count_row = await db.execute(
        select(func.count(Invoice.id)).where(Invoice.client_lot_id == renego.client_lot_id)
    )
    existing_count = count_row.scalar() or 0

    for i in range(renego.new_installments):
        due = renego.first_due_date + timedelta(days=30 * i)
        new_inv = Invoice(
            company_id=company_id,
            client_lot_id=renego.client_lot_id,
            due_date=due,
            amount=installment_value,
            installment_number=existing_count + i + 1,
            status=InvoiceStatus.PENDING,
        )
        db.add(new_inv)
        await db.flush()
        new_invoice_ids.append(str(new_inv.id))

    renego.new_invoice_ids = new_invoice_ids
    renego.status = RenegotiationStatus.APPLIED
    renego.applied_at = datetime.now(timezone.utc)

    # Update client status
    client_row = await db.execute(
        select(Client).where(Client.id == renego.client_id)
    )
    client = client_row.scalar_one_or_none()
    if client and client.status == ClientStatus.DEFAULTER:
        client.status = ClientStatus.IN_NEGOTIATION

    await record_event(
        db,
        company_id=company_id,
        client_id=renego.client_id,
        client_lot_id=renego.client_lot_id,
        event_type=ContractEventType.RENEGOTIATION,
        description=f"Renegociação aplicada: {renego.new_installments} novas parcelas de R${installment_value}",
        amount=renego.final_amount,
        metadata_json={"new_invoice_ids": new_invoice_ids},
        performed_by=admin_id,
    )

    await db.flush()
    logger.info("renegotiation_applied", renego_id=str(renego_id))
    return renego
