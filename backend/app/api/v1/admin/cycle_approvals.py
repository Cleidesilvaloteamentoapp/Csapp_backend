
"""Admin endpoints for managing cycle approval requests."""

from datetime import datetime, timezone

from dateutil.relativedelta import relativedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
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
    CycleForceApproveRequest,
    CyclePendingCountResponse,
    CycleRejectRequest,
    CycleRequestRequest,
    DeedChecklistResponse,
    DeedChecklistUpdate,
)
from app.schemas.financial_settings import rate_to_percent
from app.schemas.lot import EffectiveRatesResponse
from app.services.client_lot_service import (
    get_boleto_liquidated_invoice_ids,
    get_remaining_installments,
)
from app.services.contract_history_service import record_event
from app.services.cycle_release_service import (
    dispatch as dispatch_batch,
    enqueue_cycle_boletos,
)
from app.services.deed_checklist_service import (
    ensure_deed_checklist,
    uploaded_document_types,
)
from app.services.financial_defaults_service import get_all_effective_rates
from app.services.index_service import calculate_adjusted_value, get_accumulated_index
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/cycle-approvals", tags=["Admin Cycle Approvals"])


async def _cycle_settlement(
    db: AsyncSession, cl: ClientLot
) -> tuple[int, int, int, Decimal]:
    """How much of the contract's current cycle is actually settled.

    Only installments closed by a LIQUIDADO boleto count -- the same rule the
    renewal trigger uses, so the panel and the alert never disagree.
    """
    cycle_size = 12
    cycle_start = (cl.current_cycle - 1) * cycle_size
    cycle_end = cl.current_cycle * cycle_size

    rows = await db.execute(
        select(Invoice).where(
            Invoice.client_lot_id == cl.id,
            Invoice.installment_number > cycle_start,
            Invoice.installment_number <= cycle_end,
            Invoice.status != InvoiceStatus.CANCELLED,
        )
    )
    invoices = list(rows.scalars().all())
    if not invoices:
        return 0, 0, 0, Decimal("0")

    liquidated_ids = await get_boleto_liquidated_invoice_ids(db, cl.id)
    unpaid = [
        inv for inv in invoices
        if inv.status != InvoiceStatus.PAID or inv.id not in liquidated_ids
    ]
    today = datetime.now(timezone.utc).date()
    overdue = sum(
        (inv.amount for inv in unpaid if inv.due_date < today), Decimal("0")
    )
    return len(invoices), len(invoices) - len(unpaid), len(unpaid), overdue


async def _enrich_approval(
    db: AsyncSession, ap: CycleApproval
) -> CycleApprovalWithClientResponse:
    """Build the enriched approval response with rates, previous adjustment and suggestion."""
    cl = ap.client_lot
    client_name = lot_identifier = total_installments = None
    effective_rates = last_adjustment_date = previous_adjustment_details = None
    suggested_new_value = suggested_adjustment_details = None
    remaining_installments = installments_to_generate = None

    cycle_installments = cycle_settled = cycle_unpaid = None
    cycle_overdue_amount = None
    can_approve = True
    blocked_reason = None

    if cl:
        total_installments = cl.total_installments
        last_adjustment_date = cl.last_adjustment_date

        # Recompute settlement on read: the renewal is raised ahead of the
        # cycle's last due date, so payments keep landing after the snapshot.
        (
            cycle_installments,
            cycle_settled,
            cycle_unpaid,
            cycle_overdue_amount,
        ) = await _cycle_settlement(db, cl)
        if ap.status == CycleApprovalStatus.PENDING and cycle_unpaid:
            can_approve = False
            blocked_reason = (
                f"{cycle_unpaid} parcela(s) do ciclo {ap.cycle_number - 1} ainda não "
                f"foram liquidadas. Use \"Renovar agora\" para liberar mesmo assim."
            )

        client_name = (
            await db.execute(select(Client.full_name).where(Client.id == cl.client_id))
        ).scalar_one_or_none()
        lot_data = (
            await db.execute(select(Lot.block, Lot.lot_number).where(Lot.id == cl.lot_id))
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
        cycle_installments=cycle_installments,
        cycle_settled=cycle_settled,
        cycle_unpaid=cycle_unpaid,
        cycle_overdue_amount=cycle_overdue_amount,
        can_approve=can_approve,
        blocked_reason=blocked_reason,
    )


@router.get("", response_model=list[CycleApprovalWithClientResponse])
async def list_cycle_approvals(
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_financial")),
    status_filter: Optional[str] = Query(None, alias="status", description="PENDING, APPROVED, REJECTED"),
    client_id: Optional[UUID] = Query(None, description="Only approvals for this client"),
    client_lot_id: Optional[UUID] = Query(None, description="Only approvals for this contract"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List cycle approval requests with optional status / client filters."""
    stmt = select(CycleApproval).where(CycleApproval.company_id == admin.company_id)

    if client_lot_id:
        stmt = stmt.where(CycleApproval.client_lot_id == client_lot_id)
    if client_id:
        # The contract detail screen filters by client; this used to be ignored
        # silently, returning every approval in the company.
        stmt = stmt.where(
            CycleApproval.client_lot_id.in_(
                select(ClientLot.id).where(ClientLot.client_id == client_id)
            )
        )

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


@router.get("/pending-count", response_model=CyclePendingCountResponse)
async def pending_count(
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_financial")),
):
    """Counters for the sidebar badge and the dashboard action queue.

    Deliberately separate from the list endpoint: that one enriches every row
    with rates and an index lookup, so counting through it costs hundreds of
    round-trips to render a single number.
    """
    base = (
        CycleApproval.company_id == admin.company_id,
        CycleApproval.status == CycleApprovalStatus.PENDING,
    )
    pending = (await db.execute(
        select(func.count()).select_from(CycleApproval).where(*base)
    )).scalar() or 0
    final_cycle = (await db.execute(
        select(func.count()).select_from(CycleApproval).where(
            *base, CycleApproval.is_final_cycle.is_(True)
        )
    )).scalar() or 0
    blocked = (await db.execute(
        select(func.count()).select_from(CycleApproval).where(
            *base, CycleApproval.unpaid_count > 0
        )
    )).scalar() or 0

    return CyclePendingCountResponse(
        pending=pending, final_cycle=final_cycle, blocked_by_unpaid=blocked
    )


@router.post("/request", response_model=CycleApprovalResponse, status_code=status.HTTP_201_CREATED)
async def request_cycle(
    payload: CycleRequestRequest,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_financial")),
):
    """Open a renewal now, ahead of the scheduled trigger.

    For the contract whose lead-time window has not opened yet but that the
    admin wants to renew today.
    """
    cl = (await db.execute(
        select(ClientLot).where(
            ClientLot.id == payload.client_lot_id,
            ClientLot.company_id == admin.company_id,
        )
    )).scalar_one_or_none()
    if not cl:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")

    total = cl.total_installments or 1
    highest = (await db.execute(
        select(func.max(Invoice.installment_number)).where(
            Invoice.client_lot_id == cl.id
        )
    )).scalar() or 0
    if highest >= total:
        raise HTTPException(
            status_code=409,
            detail=f"Contrato já possui as {total} parcelas geradas; não há ciclo a renovar.",
        )

    next_cycle = cl.current_cycle + 1
    existing = (await db.execute(
        select(CycleApproval).where(
            CycleApproval.client_lot_id == cl.id,
            CycleApproval.cycle_number == next_cycle,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Já existe uma solicitação para o ciclo {next_cycle} ({existing.status.value}).",
        )

    _, _, unpaid, overdue = await _cycle_settlement(db, cl)
    remaining_after = total - highest

    ap = CycleApproval(
        company_id=admin.company_id,
        client_lot_id=cl.id,
        cycle_number=next_cycle,
        status=CycleApprovalStatus.PENDING,
        previous_installment_value=cl.current_installment_value or (cl.total_value / total),
        unpaid_count=unpaid,
        overdue_amount=overdue,
        is_final_cycle=0 < remaining_after <= 12,
        admin_notes=payload.admin_notes,
    )
    db.add(ap)

    if ap.is_final_cycle:
        await ensure_deed_checklist(db, cl)

    await log_audit(
        db,
        user_id=admin.id,
        company_id=admin.company_id,
        table_name="cycle_approvals",
        operation="REQUEST",
        resource_id=str(cl.id),
        detail=f"Renovação do ciclo {next_cycle} aberta manualmente",
    )

    await db.commit()
    await db.refresh(ap)
    logger.info("cycle_requested", client_lot_id=str(cl.id), cycle=next_cycle)
    return CycleApprovalResponse.model_validate(ap)


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
    """Approve a cycle: set the new installment value and release the next batch.

    Refuses with 409 while the closing cycle still has unsettled installments;
    releasing anyway is a deliberate act, done through /force-approve.
    """
    return await _release_cycle(approval_id, payload, db, admin, forced=False)


@router.post("/{approval_id}/force-approve", response_model=CycleApprovalResponse)
async def force_approve_cycle(
    approval_id: UUID,
    payload: CycleForceApproveRequest,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_financial")),
):
    """Renovar agora: release the next cycle even with installments still open.

    For the client who has not settled the whole cycle yet but must not be left
    without boletos. The justification is stored on the approval and audited.
    """
    return await _release_cycle(approval_id, payload, db, admin, forced=True)


async def _release_cycle(
    approval_id: UUID,
    payload: CycleApproveRequest,
    db: AsyncSession,
    admin: Profile,
    *,
    forced: bool,
) -> CycleApprovalResponse:
    """Shared body of approve / force-approve so the two can never diverge."""
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

    cl_probe = (await db.execute(
        select(ClientLot).where(ClientLot.id == ap.client_lot_id)
    )).scalar_one()
    _, settled, unpaid, overdue = await _cycle_settlement(db, cl_probe)

    if unpaid and not forced:
        raise HTTPException(
            status_code=409,
            detail=(
                f"O ciclo {ap.cycle_number - 1} tem {unpaid} parcela(s) não liquidada(s) "
                f"(R${overdue} vencido). Use 'Renovar agora' com justificativa para "
                f"liberar o próximo ciclo mesmo assim."
            ),
        )

    # Keep the stored snapshot in step with what was true at release time.
    ap.unpaid_count = unpaid
    ap.overdue_amount = overdue
    if forced:
        ap.forced = True
        ap.forced_reason = getattr(payload, "justification", None)
        ap.forced_by = admin.id

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
    # relativedelta preserves the day-of-month across months (timedelta(days=30) drifts).
    next_due = (last_inv.due_date + relativedelta(months=1)) if last_inv else datetime.now(timezone.utc).date() + relativedelta(months=1)

    # Number from the highest installment ever issued, not from a count of the
    # live ones: counting re-uses numbers freed by cancelled invoices, which
    # silently duplicates installment_number on the contract.
    last_number = (await db.execute(
        select(func.max(Invoice.installment_number)).where(
            Invoice.client_lot_id == client_lot.id,
        )
    )).scalar() or 0

    total = client_lot.total_installments or 1
    invoices_to_generate = max(0, min(12, total - last_number))
    if invoices_to_generate == 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Contrato já possui as {total} parcelas geradas; "
                "não há ciclo seguinte a aprovar."
            ),
        )

    new_invoices: list[Invoice] = []
    for i in range(invoices_to_generate):
        inv = Invoice(
            company_id=admin.company_id,
            client_lot_id=client_lot.id,
            due_date=next_due,
            amount=payload.new_installment_value,
            installment_number=last_number + i + 1,
            status=InvoiceStatus.PENDING,
        )
        db.add(inv)
        new_invoices.append(inv)
        next_due = next_due + relativedelta(months=1)

    await db.flush()

    # Release the boletos for those installments. Approving used to stop at the
    # invoices, so the admin had to go and issue the carnê by hand on another
    # screen -- which is exactly where renewals stalled.
    batch, release_warning = await enqueue_cycle_boletos(
        db,
        company_id=admin.company_id,
        client_lot=client_lot,
        invoices=new_invoices,
        created_by=admin.id,
    )

    # This is the contract's last cycle: the deed has to be prepared alongside it.
    remaining_after = total - (last_number + invoices_to_generate)
    if remaining_after <= 0:
        ap.is_final_cycle = True
        await ensure_deed_checklist(db, client_lot)

    # Record event
    await record_event(
        db,
        company_id=admin.company_id,
        client_id=client_lot.client_id,
        client_lot_id=client_lot.id,
        event_type=ContractEventType.CYCLE_APPROVED,
        description=(
            f"Ciclo {ap.cycle_number} aprovado"
            + (" (RENOVAÇÃO FORÇADA)" if forced else "")
            + f". Valor anterior: R${ap.previous_installment_value}, "
            f"Novo valor: R${payload.new_installment_value}. "
            f"{invoices_to_generate} novas parcelas geradas."
            + (
                f" Liberado com {unpaid} parcela(s) em aberto. "
                f"Justificativa: {ap.forced_reason}"
                if forced
                else ""
            )
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
        operation="FORCE_APPROVE" if forced else "APPROVE",
        resource_id=str(approval_id),
        detail=(
            f"Cycle {ap.cycle_number} "
            + ("force-" if forced else "")
            + f"approved. New value: {payload.new_installment_value}"
            + (f". Unpaid: {unpaid}. Reason: {ap.forced_reason}" if forced else "")
        ),
    )

    await db.commit()
    await db.refresh(ap)

    # Enqueue only after the commit: the worker must be able to read the batch.
    dispatch_batch(batch, admin.company_id)

    logger.info(
        "cycle_approved",
        approval_id=str(approval_id),
        cycle=ap.cycle_number,
        forced=forced,
        invoices=invoices_to_generate,
        batch_id=str(batch.id) if batch else None,
        release_warning=release_warning,
    )
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


# ---------------------------------------------------------------------------
# Escrituração checklist
# ---------------------------------------------------------------------------

async def _checklist_response(
    db: AsyncSession, checklist, client_lot: ClientLot
) -> DeedChecklistResponse:
    return DeedChecklistResponse(
        id=checklist.id,
        client_lot_id=checklist.client_lot_id,
        items=checklist.items or [],
        notes=checklist.notes,
        completed_at=checklist.completed_at,
        uploaded_document_types=await uploaded_document_types(db, client_lot),
    )


async def _load_contract(db: AsyncSession, client_lot_id: UUID, company_id: UUID) -> ClientLot:
    cl = (await db.execute(
        select(ClientLot).where(
            ClientLot.id == client_lot_id,
            ClientLot.company_id == company_id,
        )
    )).scalar_one_or_none()
    if not cl:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    return cl


@router.get("/deed-checklist/{client_lot_id}", response_model=DeedChecklistResponse)
async def get_deed_checklist(
    client_lot_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_financial")),
):
    """Escrituração checklist for a contract, created on first read if needed."""
    cl = await _load_contract(db, client_lot_id, admin.company_id)
    checklist = await ensure_deed_checklist(db, cl)
    await db.commit()
    await db.refresh(checklist)
    return await _checklist_response(db, checklist, cl)


@router.patch("/deed-checklist/{client_lot_id}", response_model=DeedChecklistResponse)
async def update_deed_checklist(
    client_lot_id: UUID,
    payload: DeedChecklistUpdate,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_financial")),
):
    """Tick one checklist item, or replace the free-text notes."""
    cl = await _load_contract(db, client_lot_id, admin.company_id)
    checklist = await ensure_deed_checklist(db, cl)

    if payload.notes is not None:
        checklist.notes = payload.notes

    if payload.document_type is not None:
        items = [dict(i) for i in (checklist.items or [])]
        match = next(
            (i for i in items if i.get("document_type") == payload.document_type), None
        )
        if match is None:
            raise HTTPException(
                status_code=404,
                detail=f"Item '{payload.document_type}' não existe no checklist",
            )
        if payload.done is not None:
            match["done"] = payload.done
        if payload.note is not None:
            match["note"] = payload.note
        match["updated_at"] = datetime.now(timezone.utc).isoformat()
        # JSONB columns need a new object to be seen as dirty.
        checklist.items = items

    checklist.mark_completion()

    await log_audit(
        db,
        user_id=admin.id,
        company_id=admin.company_id,
        table_name="deed_checklists",
        operation="UPDATE",
        resource_id=str(checklist.id),
        detail=(
            f"Escrituração: {payload.document_type or 'notas'} atualizado"
            if payload.document_type or payload.notes is not None
            else "Escrituração atualizada"
        ),
    )

    await db.commit()
    await db.refresh(checklist)
    return await _checklist_response(db, checklist, cl)
