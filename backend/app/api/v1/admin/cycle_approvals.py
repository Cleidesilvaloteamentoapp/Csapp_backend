
"""Admin endpoints for managing cycle approval requests."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.database import get_db
from app.core.deps import get_company_admin, require_permission
from app.models.client import Client
from app.models.client_lot import ClientLot
from app.models.cycle_approval import CycleApproval
from app.models.enums import (
    ClientLotStatus,
    ContractEventType,
    CycleApprovalStatus,
    InvoiceStatus,
)
from app.models.invoice import Invoice
from app.models.lot import Lot
from app.models.user import Profile
from app.schemas.cycle_approval import (
    CycleApprovalResponse,
    CycleApprovalWithClientResponse,
    CycleApproveRequest,
    CycleRejectRequest,
)
from app.schemas.financial_settings import rate_to_percent
from app.schemas.lot import EffectiveRatesResponse
from app.services.client_lot_service import get_remaining_installments
from app.services.contract_history_service import record_event
from app.services.financial_defaults_service import get_all_effective_rates
from app.services.index_service import calculate_adjusted_value, get_accumulated_index
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/cycle-approvals", tags=["Admin Cycle Approvals"])


async def _enrich_approval(
    db: AsyncSession, ap: CycleApproval
) -> CycleApprovalWithClientResponse:
    """Build the enriched approval response with rates, previous adjustment and suggestion."""
    cl = ap.client_lot
    client_name = lot_identifier = total_installments = None
    effective_rates = last_adjustment_date = previous_adjustment_details = None
    suggested_new_value = suggested_adjustment_details = None
    remaining_installments = installments_to_generate = None

    if cl:
        total_installments = cl.total_installments
        last_adjustment_date = cl.last_adjustment_date

        client_name = (
            await db.execute(select(Client.full_name).where(Client.id == cl.client_id))
        ).scalar_one_or_none()
        lot_data = (
            await db.execute(select(Lot.block, Lot.number).where(Lot.id == cl.lot_id))
        ).one_or_none()
        if lot_data:
            lot_identifier = f"Qd {lot_data[0]} Lt {lot_data[1]}"

        # Effective rates currently applied to the contract.
        rates = await get_all_effective_rates(db, cl)
        effective_rates = EffectiveRatesResponse(
            penalty_rate=rate_to_percent(rates["penalty_rate"]),
            daily_interest_rate=rate_to_percent(rates["daily_interest_rate"]),
            adjustment_index=rates["adjustment_index"].value,
            adjustment_frequency=rates["adjustment_frequency"].value,
            adjustment_custom_rate=rate_to_percent(rates["adjustment_custom_rate"]),
        )

        # Cycle debit (how many parcelas remain / will be generated, e.g. "12 de 24").
        try:
            info = await get_remaining_installments(db, cl.id)
            remaining_installments = info.remaining_installments
            installments_to_generate = min(12, info.remaining_installments)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("remaining_installments_failed", approval_id=str(ap.id), error=str(exc))

        # Previously applied adjustment (most recent approved cycle before this one).
        prev = (
            await db.execute(
                select(CycleApproval)
                .where(
                    CycleApproval.client_lot_id == cl.id,
                    CycleApproval.status == CycleApprovalStatus.APPROVED,
                    CycleApproval.cycle_number < ap.cycle_number,
                )
                .order_by(CycleApproval.cycle_number.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if prev:
            previous_adjustment_details = prev.adjustment_details

        # Server-computed suggestion (IPCA accumulated + fixed rate) for pending approvals.
        if ap.status == CycleApprovalStatus.PENDING:
            try:
                index_pct = await get_accumulated_index(
                    rates["adjustment_index"], db=db, company_id=cl.company_id, months=12
                )
                custom_pct = rates["adjustment_custom_rate"] * Decimal("100")
                base = ap.previous_installment_value or cl.current_installment_value
                if base is not None:
                    calc = calculate_adjusted_value(base, index_pct, custom_pct)
                    suggested_new_value = calc["new_value"]
                    suggested_adjustment_details = {
                        k: (str(v) if isinstance(v, Decimal) else v) for k, v in calc.items()
                    }
            except Exception as exc:
                logger.warning("cycle_suggestion_failed", approval_id=str(ap.id), error=str(exc))

    return CycleApprovalWithClientResponse(
        **CycleApprovalResponse.model_validate(ap).model_dump(),
        client_name=client_name,
        lot_identifier=lot_identifier,
        total_installments=total_installments,
        effective_rates=effective_rates,
        last_adjustment_date=last_adjustment_date,
        previous_adjustment_details=previous_adjustment_details,
        suggested_new_value=suggested_new_value,
        suggested_adjustment_details=suggested_adjustment_details,
        remaining_installments=remaining_installments,
        installments_to_generate=installments_to_generate,
    )


@router.get("", response_model=list[CycleApprovalWithClientResponse])
async def list_cycle_approvals(
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_financial")),
    status_filter: Optional[str] = Query(None, alias="status", description="PENDING, APPROVED, REJECTED"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List cycle approval requests with optional status filter."""
    stmt = select(CycleApproval).where(CycleApproval.company_id == admin.company_id)

    if status_filter:
        try:
            s = CycleApprovalStatus(status_filter.upper())
            stmt = stmt.where(CycleApproval.status == s)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")

    stmt = stmt.order_by(CycleApproval.requested_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    approvals = result.scalars().all()

    return [await _enrich_approval(db, ap) for ap in approvals]


@router.get("/{approval_id}", response_model=CycleApprovalWithClientResponse)
async def get_cycle_approval(
    approval_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_financial")),
):
    """Get a single cycle approval with details."""
    row = await db.execute(
        select(CycleApproval).where(
            CycleApproval.id == approval_id,
            CycleApproval.company_id == admin.company_id,
        )
    )
    ap = row.scalar_one_or_none()
    if not ap:
        raise HTTPException(status_code=404, detail="Cycle approval not found")

    return await _enrich_approval(db, ap)


@router.post("/{approval_id}/approve", response_model=CycleApprovalResponse)
async def approve_cycle(
    approval_id: UUID,
    payload: CycleApproveRequest,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_financial")),
):
    """Approve a cycle: set new installment value and generate next 12 invoices."""
    row = await db.execute(
        select(CycleApproval).where(
            CycleApproval.id == approval_id,
            CycleApproval.company_id == admin.company_id,
            CycleApproval.status == CycleApprovalStatus.PENDING,
        )
    )
    ap = row.scalar_one_or_none()
    if not ap:
        raise HTTPException(status_code=404, detail="Pending cycle approval not found")

    # Update approval
    ap.status = CycleApprovalStatus.APPROVED
    ap.new_installment_value = payload.new_installment_value
    ap.adjustment_details = payload.adjustment_details
    ap.admin_notes = payload.admin_notes
    ap.approved_by = admin.id
    ap.approved_at = datetime.now(timezone.utc)

    # Update client_lot
    cl_row = await db.execute(select(ClientLot).where(ClientLot.id == ap.client_lot_id))
    client_lot = cl_row.scalar_one()
    client_lot.current_installment_value = payload.new_installment_value
    client_lot.current_cycle = ap.cycle_number
    client_lot.last_adjustment_date = datetime.now(timezone.utc).date()
    client_lot.last_cycle_paid_at = datetime.now(timezone.utc).date()

    # Generate next 12 invoices
    from datetime import timedelta

    # Find last invoice due date
    last_inv_row = await db.execute(
        select(Invoice)
        .where(
            Invoice.client_lot_id == client_lot.id,
            Invoice.status != InvoiceStatus.CANCELLED,
        )
        .order_by(Invoice.due_date.desc())
        .limit(1)
    )
    last_inv = last_inv_row.scalar_one_or_none()
    next_due = (last_inv.due_date + timedelta(days=30)) if last_inv else datetime.now(timezone.utc).date() + timedelta(days=30)

    # Count existing invoices for numbering
    count_row = await db.execute(
        select(Invoice)
        .where(
            Invoice.client_lot_id == client_lot.id,
            Invoice.status != InvoiceStatus.CANCELLED,
        )
    )
    existing_count = len(list(count_row.scalars().all()))

    total = client_lot.total_installments or 1
    invoices_to_generate = min(12, total - existing_count)

    for i in range(invoices_to_generate):
        inv = Invoice(
            company_id=admin.company_id,
            client_lot_id=client_lot.id,
            due_date=next_due,
            amount=payload.new_installment_value,
            installment_number=existing_count + i + 1,
            status=InvoiceStatus.PENDING,
        )
        db.add(inv)
        next_due = next_due + timedelta(days=30)

    # Record event
    await record_event(
        db,
        company_id=admin.company_id,
        client_id=client_lot.client_id,
        client_lot_id=client_lot.id,
        event_type=ContractEventType.CYCLE_APPROVED,
        description=(
            f"Ciclo {ap.cycle_number} aprovado. "
            f"Valor anterior: R${ap.previous_installment_value}, "
            f"Novo valor: R${payload.new_installment_value}. "
            f"{invoices_to_generate} novas parcelas geradas."
        ),
        amount=payload.new_installment_value,
        previous_value=str(ap.previous_installment_value),
        new_value=str(payload.new_installment_value),
        performed_by=admin.id,
        metadata_json=payload.adjustment_details,
    )

    await log_audit(
        db,
        user_id=admin.id,
        company_id=admin.company_id,
        table_name="cycle_approvals",
        operation="APPROVE",
        resource_id=str(approval_id),
        detail=f"Cycle {ap.cycle_number} approved. New value: {payload.new_installment_value}",
    )

    await db.commit()
    await db.refresh(ap)
    logger.info("cycle_approved", approval_id=str(approval_id), cycle=ap.cycle_number)
    return CycleApprovalResponse.model_validate(ap)


@router.post("/{approval_id}/reject", response_model=CycleApprovalResponse)
async def reject_cycle(
    approval_id: UUID,
    payload: CycleRejectRequest,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_financial")),
):
    """Reject a cycle approval request."""
    row = await db.execute(
        select(CycleApproval).where(
            CycleApproval.id == approval_id,
            CycleApproval.company_id == admin.company_id,
            CycleApproval.status == CycleApprovalStatus.PENDING,
        )
    )
    ap = row.scalar_one_or_none()
    if not ap:
        raise HTTPException(status_code=404, detail="Pending cycle approval not found")

    ap.status = CycleApprovalStatus.REJECTED
    ap.admin_notes = payload.admin_notes
    ap.approved_by = admin.id
    ap.approved_at = datetime.now(timezone.utc)

    await log_audit(
        db,
        user_id=admin.id,
        company_id=admin.company_id,
        table_name="cycle_approvals",
        operation="REJECT",
        resource_id=str(approval_id),
        detail=f"Cycle {ap.cycle_number} rejected: {payload.admin_notes}",
    )

    await db.commit()
    await db.refresh(ap)
    logger.info("cycle_rejected", approval_id=str(approval_id))
    return CycleApprovalResponse.model_validate(ap)
