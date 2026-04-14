
"""Admin endpoints for debt renegotiation management."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_company_admin, require_permission
from app.models.enums import RenegotiationStatus
from app.models.renegotiation import Renegotiation
from app.models.user import Profile
from app.schemas.renegotiation import (
    RenegotiationApprove,
    RenegotiationCreate,
    RenegotiationResponse,
)
from app.services import renegotiation_service
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/renegotiations", tags=["Admin Renegotiations"])


@router.get("", response_model=list[RenegotiationResponse])
async def list_renegotiations(
    client_id: Optional[UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_renegotiations")),
):
    """List renegotiations with optional filters."""
    stmt = select(Renegotiation).where(Renegotiation.company_id == admin.company_id)

    if client_id:
        stmt = stmt.where(Renegotiation.client_id == client_id)
    if status_filter:
        try:
            s = RenegotiationStatus(status_filter)
            stmt = stmt.where(Renegotiation.status == s)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")

    stmt = stmt.order_by(Renegotiation.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return [RenegotiationResponse.model_validate(r) for r in result.scalars().all()]


@router.get("/debt-summary/{client_id}/{client_lot_id}")
async def get_debt_summary(
    client_id: UUID,
    client_lot_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_renegotiations")),
):
    """Calculate current overdue debt for a client contract."""
    debt = await renegotiation_service.calculate_debt(
        db, admin.company_id, client_id, client_lot_id
    )
    return {
        "overdue_count": debt["overdue_count"],
        "total_principal": float(debt["total_principal"]),
        "total_penalty": float(debt["total_penalty"]),
        "total_interest": float(debt["total_interest"]),
        "total_debt": float(debt["total_debt"]),
    }


@router.post("", response_model=RenegotiationResponse, status_code=status.HTTP_201_CREATED)
async def create_renegotiation(
    data: RenegotiationCreate,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_renegotiations")),
):
    """Create a renegotiation proposal for overdue debt."""
    try:
        renego = await renegotiation_service.create_renegotiation(
            db, admin.company_id, admin.id,
            client_id=data.client_id,
            client_lot_id=data.client_lot_id,
            discount_amount=data.discount_amount,
            penalty_waived=data.penalty_waived,
            interest_waived=data.interest_waived,
            new_installments=data.new_installments,
            first_due_date=data.first_due_date,
            reason=data.reason,
            admin_notes=data.admin_notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RenegotiationResponse.model_validate(renego)


@router.get("/{renego_id}", response_model=RenegotiationResponse)
async def get_renegotiation(
    renego_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_renegotiations")),
):
    """Get renegotiation details."""
    row = await db.execute(
        select(Renegotiation).where(
            Renegotiation.id == renego_id,
            Renegotiation.company_id == admin.company_id,
        )
    )
    renego = row.scalar_one_or_none()
    if not renego:
        raise HTTPException(status_code=404, detail="Renegotiation not found")
    return RenegotiationResponse.model_validate(renego)


@router.post("/{renego_id}/approve", response_model=RenegotiationResponse)
async def approve_renegotiation(
    renego_id: UUID,
    data: RenegotiationApprove,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_renegotiations")),
):
    """Approve or reject a renegotiation proposal."""
    try:
        renego = await renegotiation_service.approve_renegotiation(
            db, admin.company_id, admin.id, renego_id,
            approved=data.approved,
            admin_notes=data.admin_notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RenegotiationResponse.model_validate(renego)


@router.post("/{renego_id}/apply", response_model=RenegotiationResponse)
async def apply_renegotiation(
    renego_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_renegotiations")),
):
    """Apply an approved renegotiation: cancel old invoices and create new ones."""
    try:
        renego = await renegotiation_service.apply_renegotiation(
            db, admin.company_id, admin.id, renego_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RenegotiationResponse.model_validate(renego)
