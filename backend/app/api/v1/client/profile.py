from typing import Optional

"""Client profile endpoints – view and update own profile."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.database import get_db
from app.core.deps import get_client_user
from app.models.client import Client
from app.models.user import Profile
from app.schemas.client import ClientProfileResponse, ClientProfileUpdate
from app.services.storage_service import get_public_url, upload_file
from app.utils.exceptions import StorageError

router = APIRouter(prefix="/profile", tags=["Client Profile"])


def _profile_response(client: Client) -> ClientProfileResponse:
    """Serialize the client profile, resolving the stored photo path to a URL."""
    resp = ClientProfileResponse.model_validate(client)
    if client.photo_url:
        try:
            resp.photo_url = get_public_url(client.photo_url)
        except Exception:
            pass
    return resp


async def _get_client(db: AsyncSession, user: Profile) -> Client:
    """Retrieve the Client record linked to the current profile."""
    row = await db.execute(
        select(Client).where(
            Client.profile_id == user.id,
            Client.company_id == user.company_id,
        )
    )
    client = row.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client profile not found")
    return client


@router.get("", response_model=ClientProfileResponse)
async def get_profile(
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Return the authenticated client's profile data."""
    client = await _get_client(db, user)
    return _profile_response(client)


@router.patch("", response_model=ClientProfileResponse)
async def update_profile(
    updates: ClientProfileUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Update limited fields on the client's own profile."""
    client = await _get_client(db, user)

    changed_fields = {}
    for field, value in updates.model_dump(exclude_unset=True).items():
        old_value = getattr(client, field, None)
        if value != old_value:
            setattr(client, field, value)
            changed_fields[field] = {"old": str(old_value), "new": str(value)}

    if not changed_fields:
        return _profile_response(client)

    client.updated_at = datetime.now(timezone.utc)
    await db.flush()

    await log_audit(
        db,
        user_id=user.id,
        company_id=user.company_id,
        table_name="clients",
        operation="CLIENT_PROFILE_UPDATE",
        resource_id=str(client.id),
        detail=str(changed_fields),
        ip_address=request.client.host if request.client else None,
    )

    return _profile_response(client)


@router.post("/photo", response_model=ClientProfileResponse)
async def upload_profile_photo(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Upload/replace the authenticated client's own profile photo."""
    client = await _get_client(db, user)

    try:
        contents = await file.read()
        path = await upload_file(
            file_bytes=contents,
            original_filename=file.filename or "photo",
            company_id=str(user.company_id),
            subfolder=f"clients/{client.id}/photo",
        )
    except StorageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.detail) from exc

    client.photo_url = path
    await db.flush()

    await log_audit(
        db,
        user_id=user.id,
        company_id=user.company_id,
        table_name="clients",
        operation="CLIENT_PROFILE_PHOTO",
        resource_id=str(client.id),
        detail="Foto de perfil atualizada pelo cliente",
        ip_address=request.client.host if request.client else None,
    )

    return _profile_response(client)
