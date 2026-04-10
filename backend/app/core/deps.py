
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

# Custom bearer scheme that logs authorization header
class DebugHTTPBearer(HTTPBearer):
    async def __call__(self, request: Request):
        auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
        logger.info(f"[BEARER] Raw auth header: {auth_header[:50] if auth_header else 'NONE'}...")
        result = await super().__call__(request)
        logger.info(f"[BEARER] Parsed credentials: {result is not None}")
        return result

bearer_scheme = DebugHTTPBearer(auto_error=False)


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
    # DEBUG: Log headers
    logger.info(f"[AUTH] Path: {request.url.path}")
    logger.info(f"[AUTH] Authorization header: {request.headers.get('authorization', 'NOT PRESENT')[:50]}...")
    logger.info(f"[AUTH] Credentials from bearer_scheme: {credentials is not None}")
    
    if credentials is None:
        logger.warning(f"[AUTH] Missing credentials for path: {request.url.path}")
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

    if not profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
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
get_staff_user = require_roles(UserRole.SUPER_ADMIN, UserRole.COMPANY_ADMIN, UserRole.STAFF)


def require_permission(permission: str):
    """Return a dependency that checks a granular permission flag for STAFF users.
    SUPER_ADMIN and COMPANY_ADMIN always pass. STAFF must have the flag set to True."""

    async def _check(
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
        db: AsyncSession = Depends(get_db),
    ) -> Profile:
        current_user = await get_current_user(request, credentials, db)
        user_role = (
            current_user.role.value
            if hasattr(current_user.role, "value")
            else current_user.role
        )
        logger.info(f"[PERMISSION] Checking '{permission}' for user {current_user.id} with role: {user_role}")
        
        # SUPER_ADMIN e COMPANY_ADMIN têm acesso total sem verificar permissões
        if user_role in (UserRole.SUPER_ADMIN.value, UserRole.COMPANY_ADMIN.value):
            logger.info(f"[PERMISSION] BYPASS granted for {user_role}")
            return current_user
        
        # Outros roles (não STAFF) não têm acesso
        if user_role != UserRole.STAFF.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
        
        # Carregar staff_permission explicitamente para STAFF
        from app.models.staff_permission import StaffPermission
        result = await db.execute(
            select(StaffPermission).where(StaffPermission.profile_id == current_user.id)
        )
        perm = result.scalar_one_or_none()
        
        if perm is None or not getattr(perm, permission, False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {permission}",
            )
        return current_user

    return _check
