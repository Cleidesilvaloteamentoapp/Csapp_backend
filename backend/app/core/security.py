
"""JWT token handling (HS256 internal + ES256 Supabase), password hashing, and role checks."""

import json
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.utils.exceptions import InvalidTokenError

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserRole(str, Enum):
    """System-wide user roles."""

    SUPER_ADMIN = "SUPER_ADMIN"
    COMPANY_ADMIN = "COMPANY_ADMIN"
    CLIENT = "CLIENT"


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


# ---------------------------------------------------------------------------
# Internal JWT (HS256)
# ---------------------------------------------------------------------------

def create_access_token(
    user_id: str,
    company_id: Optional[str],
    role: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create an HS256 access token with user claims."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": user_id,
        "company_id": company_id,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(
    user_id: str,
    company_id: Optional[str],
    role: str,
) -> str:
    """Create an HS256 refresh token with extended expiry."""
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "company_id": company_id,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_internal_token(token: str) -> dict:
    """Decode and validate an internal HS256 JWT. Returns the payload dict."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("sub") is None:
            raise InvalidTokenError("Token missing subject claim")
        return payload
    except JWTError as exc:
        raise InvalidTokenError(f"Invalid token: {exc}") from exc


# ---------------------------------------------------------------------------
# Supabase JWT (ES256)
# ---------------------------------------------------------------------------

def decode_supabase_token(token: str) -> dict:
    """Decode and validate a Supabase ES256 JWT using the project JWK."""
    try:
        jwk = settings.supabase_jwt_jwk
        payload = jwt.decode(
            token,
            jwk,
            algorithms=["ES256"],
            options={"verify_aud": False},
        )
        if payload.get("sub") is None:
            raise InvalidTokenError("Supabase token missing subject claim")
        return payload
    except JWTError as exc:
        raise InvalidTokenError(f"Invalid Supabase token: {exc}") from exc


# ---------------------------------------------------------------------------
# Unified token decoder
# ---------------------------------------------------------------------------

def decode_token(token: str) -> dict:
    """Try internal HS256 first, fall back to Supabase ES256."""
    try:
        return decode_internal_token(token)
    except InvalidTokenError:
        return decode_supabase_token(token)


# ---------------------------------------------------------------------------
# Role / permission helpers
# ---------------------------------------------------------------------------

def require_role(user_role: str, allowed_roles: list[UserRole]) -> None:
    """Raise if the user role is not in the allowed set."""
    from app.utils.exceptions import InsufficientPermissionsError

    if user_role not in [r.value for r in allowed_roles]:
        raise InsufficientPermissionsError(
            f"Role '{user_role}' is not allowed. Required: {[r.value for r in allowed_roles]}"
        )
