from typing import Optional

"""Company management endpoints (super_admin only)."""

import math
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_super_admin
from app.models.company import Company
from app.models.enums import CompanyStatus
from app.models.user import Profile
from app.schemas.common import PaginatedResponse
from app.models.enums import UserRole
from app.schemas.company import (
    CompanyCreate,
    CompanyResponse,
    CompanyStatusUpdate,
    CompanyUpdate,
)
from app.schemas.superadmin import SuperadminCreateRequest, SuperadminResponse
from app.services import superadmin_service
from app.utils.exceptions import AuthenticationError, ResourceNotFoundError
from app.utils.enum_filters import parse_enum_filter

router = APIRouter(prefix="/companies", tags=["Companies"])


@router.get("", response_model=PaginatedResponse[CompanyResponse])
async def list_companies(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _admin: Profile = Depends(get_super_admin),
):
    """List all companies (super_admin only)."""
    base = select(Company)

    if status_filter:
        base = base.where(Company.status == parse_enum_filter(CompanyStatus, status_filter))
    if search:
        base = base.where(Company.name.ilike(f"%{search}%"))

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0

    rows = await db.execute(
        base.order_by(Company.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    items = [CompanyResponse.model_validate(c) for c in rows.scalars().all()]

    return PaginatedResponse[CompanyResponse](
        items=items, total=total, page=page, per_page=per_page,
        pages=math.ceil(total / per_page) if per_page else 0,
    )


@router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
async def create_company(
    data: CompanyCreate,
    db: AsyncSession = Depends(get_db),
    _admin: Profile = Depends(get_super_admin),
):
    """Create a new company."""
    existing = await db.execute(select(Company).where(Company.slug == data.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already exists")

    company = Company(name=data.name, slug=data.slug, settings=data.settings or {})
    db.add(company)
    await db.flush()
    return CompanyResponse.model_validate(company)


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    _admin: Profile = Depends(get_super_admin),
):
    """Get company details."""
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return CompanyResponse.model_validate(company)


@router.put("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: UUID,
    data: CompanyUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: Profile = Depends(get_super_admin),
):
    """Update a company."""
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(company, field, value)

    await db.flush()
    return CompanyResponse.model_validate(company)


@router.patch("/{company_id}/status", response_model=CompanyResponse)
async def update_company_status(
    company_id: UUID,
    data: CompanyStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: Profile = Depends(get_super_admin),
):
    """Activate / suspend / deactivate a company."""
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    company.status = CompanyStatus(data.status)
    await db.flush()
    return CompanyResponse.model_validate(company)


@router.get("/{company_id}/admins", response_model=list[SuperadminResponse])
async def list_company_admins(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    _admin: Profile = Depends(get_super_admin),
):
    """Administrators of a company, so a platform admin can see who runs it."""
    rows = await db.execute(
        select(Profile)
        .where(
            Profile.company_id == company_id,
            Profile.role.in_([UserRole.SUPER_ADMIN, UserRole.COMPANY_ADMIN]),
        )
        .order_by(Profile.created_at.asc())
    )
    return [SuperadminResponse.model_validate(p) for p in rows.scalars().all()]


@router.post(
    "/{company_id}/admins",
    response_model=SuperadminResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_company_admin(
    company_id: UUID,
    data: SuperadminCreateRequest,
    db: AsyncSession = Depends(get_db),
    _admin: Profile = Depends(get_super_admin),
):
    """Create the administrator of a company.

    Creating a company used to produce a shell nobody could log into: no
    endpoint could make a COMPANY_ADMIN, and /admin/superadmins hard-coded the
    caller's own company. This is what makes the reseller flow actually work.
    """
    company = (await db.execute(
        select(Company).where(Company.id == company_id)
    )).scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    try:
        profile = await superadmin_service.create_superadmin(
            data=data,
            company_id=company_id,
            db=db,
            role=UserRole.COMPANY_ADMIN,
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.detail) from exc

    await db.commit()
    await db.refresh(profile)
    return SuperadminResponse.model_validate(profile)

