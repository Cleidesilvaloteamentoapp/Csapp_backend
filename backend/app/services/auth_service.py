
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
        logger.warning("signup_conflict", reason="slug_taken")
        raise AuthenticationError("Registration failed: duplicate data detected")

    # Check email uniqueness
    existing_email = await db.execute(select(Profile).where(Profile.email == data.email))
    if existing_email.scalar_one_or_none():
        logger.warning("signup_conflict", reason="email_taken")
        raise AuthenticationError("Registration failed: duplicate data detected")

    # Check CPF/CNPJ uniqueness
    existing_cpf = await db.execute(select(Profile).where(Profile.cpf_cnpj == data.cpf_cnpj))
    if existing_cpf.scalar_one_or_none():
        logger.warning("signup_conflict", reason="cpf_cnpj_taken")
        raise AuthenticationError("Registration failed: duplicate data detected")

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


async def forgot_password(email: str, db: AsyncSession) -> bool:
    """Send password reset email to user.

    Always returns True to prevent email enumeration attacks.
    """
    from app.services.email_service import send_password_reset_email

    result = await db.execute(select(Profile).where(Profile.email == email))
    profile = result.scalar_one_or_none()

    if profile is None:
        # Don't reveal if email exists
        logger.info("forgot_password_email_not_found", email=email)
        return True

    if profile.hashed_password is None:
        # User has no password (e.g., OAuth-only)
        logger.warning("forgot_password_no_password", email=email, user_id=str(profile.id))
        return True

    # Generate short-lived reset token (15 minutes)
    from datetime import timedelta

    from app.core.security import create_access_token

    reset_token = create_access_token(
        user_id=str(profile.id),
        company_id=str(profile.company_id) if profile.company_id else None,
        role="password_reset",  # Special role for password reset
        expires_delta=timedelta(minutes=15),
    )

    # Send email
    await send_password_reset_email(email, reset_token)

    logger.info("forgot_password_email_sent", email=email, user_id=str(profile.id))
    return True


async def reset_password(token: str, new_password: str, db: AsyncSession) -> None:
    """Reset user password with valid reset token."""
    from app.core.security import decode_internal_token, hash_password

    try:
        payload = decode_internal_token(token)
    except InvalidTokenError as exc:
        logger.warning("reset_password_invalid_token", error=str(exc))
        raise AuthenticationError("Invalid or expired reset token") from exc

    # Verify this is a password reset token
    if payload.get("role") != "password_reset":
        logger.warning("reset_password_wrong_token_type", role=payload.get("role"))
        raise AuthenticationError("Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationError("Invalid token: missing user ID")

    result = await db.execute(select(Profile).where(Profile.id == UUID(user_id)))
    profile = result.scalar_one_or_none()

    if profile is None:
        raise ResourceNotFoundError("User")

    # Update password
    profile.hashed_password = hash_password(new_password)
    db.add(profile)
    await db.flush()

    logger.info("password_reset_success", user_id=str(profile.id))


async def change_password(
    user_id: UUID,
    current_password: str,
    new_password: str,
    db: AsyncSession,
) -> None:
    """Change password for logged-in user (requires current password)."""
    result = await db.execute(select(Profile).where(Profile.id == user_id))
    profile = result.scalar_one_or_none()

    if profile is None:
        raise ResourceNotFoundError("User")

    if profile.hashed_password is None:
        raise AuthenticationError("No password set for this account")

    if not verify_password(current_password, profile.hashed_password):
        logger.warning("change_password_wrong_current", user_id=str(user_id))
        raise AuthenticationError("Current password is incorrect")

    # Update password
    profile.hashed_password = hash_password(new_password)
    db.add(profile)
    await db.flush()

    logger.info("password_change_success", user_id=str(user_id))
