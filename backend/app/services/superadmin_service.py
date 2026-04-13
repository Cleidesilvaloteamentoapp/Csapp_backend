"""Superadmin management service – create additional superadmins for same company."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.user import Profile
from app.schemas.superadmin import SuperadminCreateRequest
from app.utils.exceptions import AuthenticationError
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def create_superadmin(
    data: SuperadminCreateRequest,
    company_id: uuid.UUID,
    db: AsyncSession,
) -> Profile:
    """Create a new superadmin user linked to the same company."""

    # Check email uniqueness
    existing_email = await db.execute(select(Profile).where(Profile.email == data.email))
    if existing_email.scalar_one_or_none():
        logger.warning("superadmin_create_conflict", reason="email_taken", email=data.email)
        raise AuthenticationError("Registration failed: email already exists")

    # Check CPF/CNPJ uniqueness
    existing_cpf = await db.execute(select(Profile).where(Profile.cpf_cnpj == data.cpf_cnpj))
    if existing_cpf.scalar_one_or_none():
        logger.warning("superadmin_create_conflict", reason="cpf_cnpj_taken", cpf_cnpj=data.cpf_cnpj)
        raise AuthenticationError("Registration failed: CPF/CNPJ already exists")

    # Create profile
    profile = Profile(
        company_id=company_id,
        role=UserRole.SUPER_ADMIN,
        full_name=data.full_name,
        email=data.email,
        cpf_cnpj=data.cpf_cnpj,
        phone=data.phone,
        hashed_password=hash_password(data.password),
    )
    db.add(profile)
    await db.flush()

    logger.info(
        "superadmin_created",
        user_id=str(profile.id),
        company_id=str(company_id),
        email=data.email,
    )

    return profile
