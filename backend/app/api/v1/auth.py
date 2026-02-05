"""Authentication endpoints: signup, login, logout, me, refresh."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
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
async def signup(data: SignupRequest, db: AsyncSession = Depends(get_db)):
    """Register a new company and its first super_admin user."""
    try:
        return await auth_service.signup(data, db)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.detail) from exc


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
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
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a refresh token for a new token pair."""
    try:
        return await auth_service.refresh_tokens(data.refresh_token, db)
    except (AuthenticationError, ResourceNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.detail
        ) from exc
