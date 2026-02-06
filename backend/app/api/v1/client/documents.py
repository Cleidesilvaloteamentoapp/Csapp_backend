from typing import Optional

"""Client document management endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_client_user
from app.models.client import Client
from app.models.user import Profile
from app.services.storage_service import delete_file, get_public_url, upload_file
from app.utils.exceptions import StorageError

router = APIRouter(prefix="/documents", tags=["Client Documents"])


async def _get_client(db: AsyncSession, user: Profile) -> Optional[Client]:
    row = await db.execute(
        select(Client).where(Client.profile_id == user.id, Client.company_id == user.company_id)
    )
    return row.scalar_one_or_none()


@router.get("/", response_model=list[dict])
async def list_documents(
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """List documents for the current client."""
    client = await _get_client(db, user)
    if not client:
        return []

    docs = client.documents or []
    return [{"path": d, "url": get_public_url(d)} for d in docs if isinstance(d, str)]


@router.post("/", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Upload a document for the current client."""
    client = await _get_client(db, user)
    if not client:
        raise HTTPException(status_code=404, detail="Client profile not found")

    try:
        contents = await file.read()
        path = await upload_file(
            file_bytes=contents,
            original_filename=file.filename or "upload",
            company_id=str(user.company_id),
            subfolder=f"clients/{client.id}/documents",
        )
    except StorageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.detail) from exc

    docs = list(client.documents or [])
    docs.append(path)
    client.documents = docs
    await db.flush()

    return {"path": path, "url": get_public_url(path)}


@router.delete("/{doc_index}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_document(
    doc_index: int,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Remove a document by its index in the documents array."""
    client = await _get_client(db, user)
    if not client:
        raise HTTPException(status_code=404, detail="Client profile not found")

    docs = list(client.documents or [])
    if doc_index < 0 or doc_index >= len(docs):
        raise HTTPException(status_code=404, detail="Document index out of range")

    path = docs.pop(doc_index)
    try:
        await delete_file(path)
    except StorageError:
        pass  # File may already be deleted in storage

    client.documents = docs
    await db.flush()
    return None
