
"""Admin endpoints for managing early payoff requests."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.database import get_db
from app.core.deps import get_company_admin
from app.models.early_payoff_request import EarlyPayoffRequest
from app.models.enums import EarlyPayoffStatus
from app.models.user import Profile
from app.schemas.early_payoff import EarlyPayoffAdminUpdate, EarlyPayoffResponse
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/early-payoff-requests", tags=["Admin Early Payoff"])


@router.get("", response_model=list[EarlyPayoffResponse])
async def list_requests(
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List early payoff requests."""
    stmt = select(EarlyPayoffRequest).where(
        EarlyPayoffRequest.company_id == admin.company_id
    )

    if status_filter:
        try:
            s = EarlyPayoffStatus(status_filter.upper())
            stmt = stmt.where(EarlyPayoffRequest.status == s)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")

    stmt = stmt.order_by(EarlyPayoffRequest.requested_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return [EarlyPayoffResponse.model_validate(r) for r in result.scalars().all()]


@router.get("/{request_id}", response_model=EarlyPayoffResponse)
async def get_request(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Get a single early payoff request."""
    row = await db.execute(
        select(EarlyPayoffRequest).where(
            EarlyPayoffRequest.id == request_id,
            EarlyPayoffRequest.company_id == admin.company_id,
        )
    )
    req = row.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Early payoff request not found")
    return EarlyPayoffResponse.model_validate(req)


@router.patch("/{request_id}", response_model=EarlyPayoffResponse)
async def update_request(
    request_id: UUID,
    payload: EarlyPayoffAdminUpdate,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Update status of an early payoff request."""
    row = await db.execute(
        select(EarlyPayoffRequest).where(
            EarlyPayoffRequest.id == request_id,
            EarlyPayoffRequest.company_id == admin.company_id,
        )
    )
    req = row.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Early payoff request not found")

    req.status = EarlyPayoffStatus(payload.status)
    if payload.admin_notes:
        req.admin_notes = payload.admin_notes

    await log_audit(
        db,
        user_id=admin.id,
        company_id=admin.company_id,
        table_name="early_payoff_requests",
        operation="UPDATE",
        resource_id=str(request_id),
        detail=f"Status → {payload.status}",
    )

    await db.commit()
    await db.refresh(req)
    return EarlyPayoffResponse.model_validate(req)
