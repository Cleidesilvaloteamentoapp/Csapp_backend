
"""FastAPI dependencies: authentication, authorization, database sessions."""
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import UserRole, decode_token
from app.models.user import Profile
from app.utils.exceptions import (
    AuthenticationError,
    InsufficientPermissionsError,
    InvalidTokenError,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Token payload dataclass
# ---------------------------------------------------------------------------

class TokenPayload:
    """Convenience wrapper around a decoded JWT payload."""

    def __init__(self, payload: dict) -> None:
        self.user_id: str = payload["sub"]
        self.company_id: Optional[str] = payload.get("company_id")
        self.role: str = payload.get("role", "client")
        self.token_type: str = payload.get("type", "access")

    @property
    def user_uuid(self) -> UUID:
        return UUID(self.user_id)

    @property
    def company_uuid(self) -> Optional[UUID]:
        return UUID(self.company_id) if self.company_id else None


# ---------------------------------------------------------------------------
# Core auth dependency
# ---------------------------------------------------------------------------

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Profile:
    """Decode the bearer token, load the profile, and populate request.state
    so that the TenantMiddleware can pick it up."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(credentials.credentials)
    except InvalidTokenError as exc:
        logger.warning("token_invalid", detail=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    token = TokenPayload(payload)

    if token.token_type == "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh tokens cannot be used for API access",
        )

    result = await db.execute(select(Profile).where(Profile.id == token.user_uuid))
    profile = result.scalar_one_or_none()

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User profile not found",
        )

    # Populate request.state for TenantMiddleware
    request.state.user_id = profile.id
    request.state.company_id = profile.company_id
    request.state.user_role = profile.role.value if hasattr(profile.role, "value") else profile.role

    return profile


# ---------------------------------------------------------------------------
# Role-based access helpers
# ---------------------------------------------------------------------------

def require_roles(*roles: UserRole):
    """Return a dependency that enforces a set of allowed roles."""

    async def _check(current_user: Profile = Depends(get_current_user)) -> Profile:
        user_role = current_user.role.value if hasattr(current_user.role, "value") else current_user.role
        allowed = [r.value for r in roles]
        if user_role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user_role}' is not allowed. Required: {allowed}",
            )
        return current_user

    return _check


# Pre-built dependency shortcuts
get_super_admin = require_roles(UserRole.SUPER_ADMIN)
get_company_admin = require_roles(UserRole.SUPER_ADMIN, UserRole.COMPANY_ADMIN)
get_client_user = require_roles(UserRole.SUPER_ADMIN, UserRole.COMPANY_ADMIN, UserRole.CLIENT)
