
"""Authentication endpoints: signup, login, logout, me, refresh."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user

_auth_limiter = Limiter(key_func=get_remote_address)
from app.models.user import Profile
from app.schemas.auth import (
    LoginRequest,
    MeResponse,
    RefreshRequest,
    SignupRequest,
    TokenResponse,
)
from app.services import auth_service
from app.utils.exceptions import AuthenticationError, ResourceNotFoundError

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@_auth_limiter.limit("3/minute")
async def signup(request: Request, data: SignupRequest, db: AsyncSession = Depends(get_db)):
    """Register a new company and its first super_admin user."""
    try:
        return await auth_service.signup(data, db)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.detail) from exc


@router.post("/login", response_model=TokenResponse)
@_auth_limiter.limit(settings.AUTH_RATE_LIMIT)
async def login(request: Request, data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate with email + password."""
    try:
        return await auth_service.login(data, db)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.detail
        ) from exc


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(current_user: Profile = Depends(get_current_user)):
    """Logout (client-side token discard; placeholder for token blocklist)."""
    return None


@router.get("/me", response_model=MeResponse)
async def me(current_user: Profile = Depends(get_current_user)):
    """Return the current authenticated user's profile."""
    return MeResponse.model_validate(current_user)


@router.post("/refresh", response_model=TokenResponse)
@_auth_limiter.limit("10/minute")
async def refresh(request: Request, data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a refresh token for a new token pair."""
    try:
        return await auth_service.refresh_tokens(data.refresh_token, db)
    except (AuthenticationError, ResourceNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.detail
        ) from exc
