
"""Admin endpoints for managing economic indices (IPCA, IGPM, CUB, INPC)."""

from typing import Optional
from uuid import UUID
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.database import get_db
from app.core.deps import get_company_admin, require_permission
from app.models.economic_index import EconomicIndex
from app.models.enums import AdjustmentIndex, IndexSource
from app.models.user import Profile
from app.schemas.economic_index import (
    EconomicIndexCreate,
    EconomicIndexResponse,
    EconomicIndexUpdate,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/economic-indices", tags=["Admin Economic Indices"])


@router.get("", response_model=list[EconomicIndexResponse])
async def list_indices(
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_financial_settings")),
    index_type: Optional[str] = Query(None, description="Filter by type: IPCA, IGPM, CUB, INPC"),
    state_code: Optional[str] = Query(None, description="Filter by state code (for CUB)"),
    start_month: Optional[date] = Query(None, description="Start reference month"),
    end_month: Optional[date] = Query(None, description="End reference month"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List economic index entries with optional filters."""
    stmt = select(EconomicIndex).where(EconomicIndex.company_id == admin.company_id)

    if index_type:
        try:
            idx = AdjustmentIndex(index_type.upper())
            stmt = stmt.where(EconomicIndex.index_type == idx)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid index_type: {index_type}")

    if state_code:
        stmt = stmt.where(EconomicIndex.state_code == state_code.upper())
    if start_month:
        stmt = stmt.where(EconomicIndex.reference_month >= start_month)
    if end_month:
        stmt = stmt.where(EconomicIndex.reference_month <= end_month)

    stmt = stmt.order_by(EconomicIndex.reference_month.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return [EconomicIndexResponse.model_validate(r) for r in result.scalars().all()]


@router.post("", response_model=EconomicIndexResponse, status_code=status.HTTP_201_CREATED)
async def create_index(
    payload: EconomicIndexCreate,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_financial_settings")),
):
    """Manually create an economic index entry."""
    # Validate CUB requires state_code
    if payload.index_type == "CUB" and not payload.state_code:
        raise HTTPException(status_code=400, detail="state_code is required for CUB index")

    # Check for duplicate
    ref_month = date(payload.reference_month.year, payload.reference_month.month, 1)
    existing_stmt = select(EconomicIndex).where(
        EconomicIndex.company_id == admin.company_id,
        EconomicIndex.index_type == AdjustmentIndex(payload.index_type),
        EconomicIndex.reference_month == ref_month,
    )
    if payload.state_code:
        existing_stmt = existing_stmt.where(
            EconomicIndex.state_code == payload.state_code.upper()
        )
    existing = (await db.execute(existing_stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Index entry already exists for this type/month/state. Use PATCH to update.",
        )

    entry = EconomicIndex(
        company_id=admin.company_id,
        index_type=AdjustmentIndex(payload.index_type),
        state_code=payload.state_code.upper() if payload.state_code else None,
        reference_month=ref_month,
        value=payload.value,
        source=IndexSource.MANUAL,
        created_by=admin.id,
    )
    db.add(entry)
    await db.flush()

    await log_audit(
        db,
        user_id=admin.id,
        company_id=admin.company_id,
        table_name="economic_indices",
        operation="CREATE",
        resource_id=str(entry.id),
        detail=f"Manual {payload.index_type} index: {payload.value} for {ref_month}",
    )

    await db.commit()
    await db.refresh(entry)
    logger.info("economic_index_created", index_id=str(entry.id))
    return EconomicIndexResponse.model_validate(entry)


@router.patch("/{index_id}", response_model=EconomicIndexResponse)
async def update_index(
    index_id: UUID,
    payload: EconomicIndexUpdate,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_financial_settings")),
):
    """Update an economic index entry."""
    result = await db.execute(
        select(EconomicIndex).where(
            EconomicIndex.id == index_id,
            EconomicIndex.company_id == admin.company_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Economic index not found")

    update_data = payload.model_dump(exclude_none=True)
    for field, value in update_data.items():
        if field == "state_code" and value:
            value = value.upper()
        setattr(entry, field, value)

    await log_audit(
        db,
        user_id=admin.id,
        company_id=admin.company_id,
        table_name="economic_indices",
        operation="UPDATE",
        resource_id=str(index_id),
        detail=f"Updated fields: {list(update_data.keys())}",
    )

    await db.commit()
    await db.refresh(entry)
    return EconomicIndexResponse.model_validate(entry)


@router.delete("/{index_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_index(
    index_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_financial_settings")),
):
    """Delete an economic index entry."""
    result = await db.execute(
        select(EconomicIndex).where(
            EconomicIndex.id == index_id,
            EconomicIndex.company_id == admin.company_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Economic index not found")

    await log_audit(
        db,
        user_id=admin.id,
        company_id=admin.company_id,
        table_name="economic_indices",
        operation="DELETE",
        resource_id=str(index_id),
        detail=f"Deleted {entry.index_type.value} for {entry.reference_month}",
    )

    await db.delete(entry)
    await db.commit()
