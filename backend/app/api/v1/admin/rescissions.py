
"""Admin endpoints for contract rescission (distrato) management."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_company_admin, require_permission
from app.models.enums import RescissionStatus
from app.models.rescission import Rescission
from app.models.user import Profile
from app.schemas.rescission import (
    RescissionApprove,
    RescissionCreate,
    RescissionResponse,
)
from app.services import rescission_service
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/rescissions", tags=["Admin Rescissions"])


@router.get("", response_model=list[RescissionResponse])
async def list_rescissions(
    client_id: Optional[UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_rescissions")),
):
    """List rescissions with optional filters."""
    stmt = select(Rescission).where(Rescission.company_id == admin.company_id)

    if client_id:
        stmt = stmt.where(Rescission.client_id == client_id)
    if status_filter:
        try:
            s = RescissionStatus(status_filter)
            stmt = stmt.where(Rescission.status == s)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")

    stmt = stmt.order_by(Rescission.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return [RescissionResponse.model_validate(r) for r in result.scalars().all()]


@router.post("", response_model=RescissionResponse, status_code=status.HTTP_201_CREATED)
async def create_rescission(
    data: RescissionCreate,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_rescissions")),
):
    """Request a contract rescission (distrato)."""
    try:
        rescission = await rescission_service.create_rescission(
            db, admin.company_id, admin.id,
            client_id=data.client_id,
            client_lot_id=data.client_lot_id,
            reason=data.reason,
            admin_notes=data.admin_notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RescissionResponse.model_validate(rescission)


@router.get("/{rescission_id}", response_model=RescissionResponse)
async def get_rescission(
    rescission_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_rescissions")),
):
    """Get rescission details."""
    row = await db.execute(
        select(Rescission).where(
            Rescission.id == rescission_id,
            Rescission.company_id == admin.company_id,
        )
    )
    rescission = row.scalar_one_or_none()
    if not rescission:
        raise HTTPException(status_code=404, detail="Rescission not found")
    return RescissionResponse.model_validate(rescission)


@router.post("/{rescission_id}/approve", response_model=RescissionResponse)
async def approve_rescission(
    rescission_id: UUID,
    data: RescissionApprove,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_rescissions")),
):
    """Approve or reject a rescission request with financial terms."""
    try:
        rescission = await rescission_service.approve_rescission(
            db, admin.company_id, admin.id, rescission_id,
            approved=data.approved,
            refund_amount=data.refund_amount,
            penalty_amount=data.penalty_amount,
            admin_notes=data.admin_notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RescissionResponse.model_validate(rescission)


@router.post("/{rescission_id}/complete", response_model=RescissionResponse)
async def complete_rescission(
    rescission_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_rescissions")),
):
    """Complete an approved rescission: cancel invoices, release lot back to inventory."""
    try:
        rescission = await rescission_service.complete_rescission(
            db, admin.company_id, admin.id, rescission_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RescissionResponse.model_validate(rescission)
