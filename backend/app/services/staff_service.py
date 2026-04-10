"""Staff account management service."""

import uuid
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.staff_permission import StaffPermission
from app.models.user import Profile
from app.schemas.staff import StaffCreateRequest, StaffUpdateRequest
from app.utils.exceptions import (
    AuthenticationError,
    ResourceNotFoundError,
    InsufficientPermissionsError,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def _get_staff_in_company(
    staff_id: uuid.UUID, company_id: uuid.UUID, db: AsyncSession
) -> Profile:
    result = await db.execute(
        select(Profile).where(
            Profile.id == staff_id,
            Profile.company_id == company_id,
            Profile.role == UserRole.STAFF,
        )
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise ResourceNotFoundError("Staff member")
    return profile


async def list_staff(company_id: uuid.UUID, db: AsyncSession) -> List[Profile]:
    result = await db.execute(
        select(Profile).where(
            Profile.company_id == company_id,
            Profile.role == UserRole.STAFF,
        )
    )
    return list(result.scalars().all())


async def get_staff(staff_id: uuid.UUID, company_id: uuid.UUID, db: AsyncSession) -> Profile:
    return await _get_staff_in_company(staff_id, company_id, db)


async def create_staff(
    data: StaffCreateRequest, company_id: uuid.UUID, db: AsyncSession
) -> Profile:
    existing_email = await db.execute(select(Profile).where(Profile.email == data.email))
    if existing_email.scalar_one_or_none():
        raise AuthenticationError("Email already registered")

    existing_cpf = await db.execute(
        select(Profile).where(Profile.cpf_cnpj == data.cpf_cnpj)
    )
    if existing_cpf.scalar_one_or_none():
        raise AuthenticationError("CPF/CNPJ already registered")

    profile = Profile(
        company_id=company_id,
        role=UserRole.STAFF,
        full_name=data.full_name,
        email=data.email,
        cpf_cnpj=data.cpf_cnpj,
        phone=data.phone,
        hashed_password=hash_password(data.password),
        is_active=True,
    )
    db.add(profile)
    await db.flush()

    perm_data = data.permissions.model_dump() if data.permissions else {}
    permission = StaffPermission(
        profile_id=profile.id,
        company_id=company_id,
        **perm_data,
    )
    db.add(permission)
    await db.flush()

    await db.refresh(profile)
    logger.info("staff_created", staff_id=str(profile.id), company_id=str(company_id))
    return profile


async def update_staff(
    staff_id: uuid.UUID,
    data: StaffUpdateRequest,
    company_id: uuid.UUID,
    db: AsyncSession,
) -> Profile:
    profile = await _get_staff_in_company(staff_id, company_id, db)

    if data.full_name is not None:
        profile.full_name = data.full_name
    if data.phone is not None:
        profile.phone = data.phone
    if data.password is not None:
        profile.hashed_password = hash_password(data.password)

    db.add(profile)

    if data.permissions is not None:
        result = await db.execute(
            select(StaffPermission).where(StaffPermission.profile_id == staff_id)
        )
        perm = result.scalar_one_or_none()
        if perm is None:
            perm = StaffPermission(
                profile_id=profile.id,
                company_id=company_id,
                **data.permissions.model_dump(),
            )
            db.add(perm)
        else:
            for field, value in data.permissions.model_dump().items():
                setattr(perm, field, value)
            db.add(perm)

    await db.flush()
    await db.refresh(profile)
    logger.info("staff_updated", staff_id=str(staff_id), company_id=str(company_id))
    return profile


async def toggle_active(
    staff_id: uuid.UUID, company_id: uuid.UUID, db: AsyncSession
) -> Profile:
    profile = await _get_staff_in_company(staff_id, company_id, db)
    profile.is_active = not profile.is_active
    db.add(profile)
    await db.flush()
    await db.refresh(profile)
    action = "activated" if profile.is_active else "deactivated"
    logger.info(f"staff_{action}", staff_id=str(staff_id), company_id=str(company_id))
    return profile


async def delete_staff(
    staff_id: uuid.UUID, company_id: uuid.UUID, db: AsyncSession
) -> None:
    profile = await _get_staff_in_company(staff_id, company_id, db)
    await db.delete(profile)
    await db.flush()
    logger.info("staff_deleted", staff_id=str(staff_id), company_id=str(company_id))
