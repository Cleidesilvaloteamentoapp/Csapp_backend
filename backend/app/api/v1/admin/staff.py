"""Admin endpoints for staff account management."""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_company_admin
from app.models.user import Profile
from app.schemas.staff import (
    StaffCreateRequest,
    StaffResponse,
    StaffToggleResponse,
    StaffUpdateRequest,
)
from app.services import staff_service
from app.utils.exceptions import AuthenticationError, ResourceNotFoundError

router = APIRouter(prefix="/staff", tags=["Admin – Staff"])


@router.get("/", response_model=List[StaffResponse])
async def list_staff(
    current_user: Profile = Depends(get_company_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all staff members in the current company."""
    members = await staff_service.list_staff(current_user.company_id, db)
    return [StaffResponse.from_profile(m) for m in members]


@router.post("/", response_model=StaffResponse, status_code=status.HTTP_201_CREATED)
async def create_staff(
    data: StaffCreateRequest,
    current_user: Profile = Depends(get_company_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new staff account in the current company."""
    try:
        profile = await staff_service.create_staff(data, current_user.company_id, db)
        return StaffResponse.from_profile(profile)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.detail) from exc


@router.get("/{staff_id}", response_model=StaffResponse)
async def get_staff(
    staff_id: uuid.UUID,
    current_user: Profile = Depends(get_company_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get a staff member's details and permissions."""
    try:
        profile = await staff_service.get_staff(staff_id, current_user.company_id, db)
        return StaffResponse.from_profile(profile)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.detail) from exc


@router.patch("/{staff_id}", response_model=StaffResponse)
async def update_staff(
    staff_id: uuid.UUID,
    data: StaffUpdateRequest,
    current_user: Profile = Depends(get_company_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a staff member's data and/or permissions."""
    try:
        profile = await staff_service.update_staff(
            staff_id, data, current_user.company_id, db
        )
        return StaffResponse.from_profile(profile)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.detail) from exc


@router.patch("/{staff_id}/toggle-active", response_model=StaffToggleResponse)
async def toggle_active(
    staff_id: uuid.UUID,
    current_user: Profile = Depends(get_company_admin),
    db: AsyncSession = Depends(get_db),
):
    """Activate or deactivate a staff account."""
    try:
        profile = await staff_service.toggle_active(staff_id, current_user.company_id, db)
        action = "activated" if profile.is_active else "deactivated"
        return StaffToggleResponse(
            id=profile.id,
            is_active=profile.is_active,
            message=f"Staff account {action} successfully",
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.detail) from exc


@router.delete("/{staff_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_staff(
    staff_id: uuid.UUID,
    current_user: Profile = Depends(get_company_admin),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete a staff account."""
    try:
        await staff_service.delete_staff(staff_id, current_user.company_id, db)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.detail) from exc
