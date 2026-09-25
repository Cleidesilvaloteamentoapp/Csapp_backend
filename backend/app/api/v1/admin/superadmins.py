"""Admin endpoints for superadmin account management."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_super_admin
from app.models.user import Profile
from app.schemas.superadmin import SuperadminCreateRequest, SuperadminResponse
from app.services import superadmin_service
from app.utils.exceptions import AuthenticationError
from app.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/superadmins", tags=["Admin – Superadmins"])


@router.get("", response_model=list[SuperadminResponse])
async def list_superadmins(
    current_user: Profile = Depends(get_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Other platform admins in this company.

    The staff screen has always called this; it did not exist, and the frontend
    swallowed the 404, so the list silently rendered empty.
    """
    from sqlalchemy import select

    from app.models.enums import UserRole

    rows = await db.execute(
        select(Profile)
        .where(
            Profile.company_id == current_user.company_id,
            Profile.role == UserRole.SUPER_ADMIN,
        )
        .order_by(Profile.created_at.asc())
    )
    return [SuperadminResponse.model_validate(p) for p in rows.scalars().all()]


@router.post("", response_model=SuperadminResponse, status_code=status.HTTP_201_CREATED)
async def create_superadmin(
    data: SuperadminCreateRequest,
    current_user: Profile = Depends(get_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new superadmin user for the same company.

    Only existing SUPER_ADMIN users can create additional superadmins.
    The new user will be linked to the same company as the creator.
    """
    try:
        profile = await superadmin_service.create_superadmin(
            data=data,
            company_id=current_user.company_id,
            db=db,
        )
        return SuperadminResponse.model_validate(profile)
    except AuthenticationError as exc:
        logger.warning(
            "superadmin_create_failed",
            reason=str(exc),
            creator_id=str(current_user.id),
            company_id=str(current_user.company_id),
            email=data.email,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.detail,
        ) from exc
