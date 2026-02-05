"""Authentication service – signup, login, token refresh."""

from uuid import UUID

from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_internal_token,
    hash_password,
    verify_password,
)
from app.models.company import Company
from app.models.enums import CompanyStatus, UserRole
from app.models.user import Profile
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse
from app.utils.exceptions import AuthenticationError, InvalidTokenError, ResourceNotFoundError
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def signup(data: SignupRequest, db: AsyncSession) -> TokenResponse:
    """Register a new company with its first super_admin user."""

    # Check slug uniqueness
    existing = await db.execute(select(Company).where(Company.slug == data.company_slug))
    if existing.scalar_one_or_none():
        raise AuthenticationError(f"Company slug '{data.company_slug}' is already taken")

    # Check email uniqueness
    existing_email = await db.execute(select(Profile).where(Profile.email == data.email))
    if existing_email.scalar_one_or_none():
        raise AuthenticationError(f"Email '{data.email}' is already registered")

    # Check CPF/CNPJ uniqueness
    existing_cpf = await db.execute(select(Profile).where(Profile.cpf_cnpj == data.cpf_cnpj))
    if existing_cpf.scalar_one_or_none():
        raise AuthenticationError(f"CPF/CNPJ '{data.cpf_cnpj}' is already registered")

    # Create company
    company = Company(
        name=data.company_name,
        slug=data.company_slug,
        status=CompanyStatus.ACTIVE,
    )
    db.add(company)
    await db.flush()

    # Create profile
    profile = Profile(
        company_id=company.id,
        role=UserRole.SUPER_ADMIN,
        full_name=data.full_name,
        email=data.email,
        cpf_cnpj=data.cpf_cnpj,
        phone=data.phone,
        hashed_password=hash_password(data.password),
    )
    db.add(profile)
    await db.flush()

    logger.info("signup_success", user_id=str(profile.id), company_id=str(company.id))

    return TokenResponse(
        access_token=create_access_token(
            user_id=str(profile.id),
            company_id=str(company.id),
            role=UserRole.SUPER_ADMIN.value,
        ),
        refresh_token=create_refresh_token(
            user_id=str(profile.id),
            company_id=str(company.id),
            role=UserRole.SUPER_ADMIN.value,
        ),
    )


async def login(data: LoginRequest, db: AsyncSession) -> TokenResponse:
    """Authenticate a user with email + password."""
    result = await db.execute(select(Profile).where(Profile.email == data.email))
    profile = result.scalar_one_or_none()

    if profile is None or profile.hashed_password is None:
        logger.warning("login_failed", email=data.email, reason="not_found")
        raise AuthenticationError("Invalid email or password")

    if not verify_password(data.password, profile.hashed_password):
        logger.warning("login_failed", email=data.email, reason="bad_password")
        raise AuthenticationError("Invalid email or password")

    logger.info("login_success", user_id=str(profile.id))

    return TokenResponse(
        access_token=create_access_token(
            user_id=str(profile.id),
            company_id=str(profile.company_id),
            role=profile.role.value,
        ),
        refresh_token=create_refresh_token(
            user_id=str(profile.id),
            company_id=str(profile.company_id),
            role=profile.role.value,
        ),
    )


async def refresh_tokens(refresh_token: str, db: AsyncSession) -> TokenResponse:
    """Exchange a valid refresh token for a new token pair."""
    try:
        payload = decode_internal_token(refresh_token)
    except InvalidTokenError as exc:
        raise AuthenticationError(f"Invalid refresh token: {exc}") from exc

    if payload.get("type") != "refresh":
        raise AuthenticationError("Token is not a refresh token")

    user_id = payload["sub"]
    result = await db.execute(select(Profile).where(Profile.id == UUID(user_id)))
    profile = result.scalar_one_or_none()

    if profile is None:
        raise ResourceNotFoundError("User")

    return TokenResponse(
        access_token=create_access_token(
            user_id=str(profile.id),
            company_id=str(profile.company_id),
            role=profile.role.value,
        ),
        refresh_token=create_refresh_token(
            user_id=str(profile.id),
            company_id=str(profile.company_id),
            role=profile.role.value,
        ),
    )
