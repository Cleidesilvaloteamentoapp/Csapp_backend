from typing import Optional

"""Client document management endpoints – uses dedicated client_documents table."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_client_user
from app.models.client import Client
from app.models.client_document import ClientDocument
from app.models.enums import DocumentStatus, DocumentType
from app.models.user import Profile
from app.schemas.client_document import ClientDocumentResponse
from app.services.storage_service import delete_file, get_public_url, upload_file
from app.utils.exceptions import StorageError

router = APIRouter(prefix="/documents", tags=["Client Documents"])

ALLOWED_CONTENT_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/jpg"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


async def _get_client(db: AsyncSession, user: Profile) -> Client:
    row = await db.execute(
        select(Client).where(Client.profile_id == user.id, Client.company_id == user.company_id)
    )
    client = row.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client profile not found")
    return client


def _enrich_response(doc: ClientDocument) -> dict:
    """Add file_url to the response."""
    resp = ClientDocumentResponse.model_validate(doc).model_dump()
    try:
        resp["file_url"] = get_public_url(doc.file_path)
    except Exception:
        resp["file_url"] = None
    return resp


@router.get("", response_model=list[ClientDocumentResponse])
async def list_documents(
    document_type: Optional[str] = None,
    doc_status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """List all structured documents for the current client."""
    client = await _get_client(db, user)

    query = select(ClientDocument).where(
        ClientDocument.client_id == client.id,
        ClientDocument.company_id == user.company_id,
    )
    if document_type:
        query = query.where(ClientDocument.document_type == document_type)
    if doc_status:
        query = query.where(ClientDocument.status == doc_status)

    query = query.order_by(ClientDocument.created_at.desc())
    rows = await db.execute(query)
    return [_enrich_response(d) for d in rows.scalars().all()]


@router.post("/upload", response_model=ClientDocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    document_type: str = Form(..., pattern=r"^(RG|CPF|COMPROVANTE_RESIDENCIA|CNH|CONTRATO|OUTROS)$"),
    file: UploadFile = File(...),
    description: Optional[str] = Form(None, max_length=500),
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Upload a document with type classification."""
    client = await _get_client(db, user)

    # Validate content type
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{file.content_type}' not allowed. Allowed: PDF, JPG, PNG",
        )

    # Read and validate size
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds maximum size of {MAX_FILE_SIZE // (1024*1024)} MB",
        )

    # Upload to Supabase Storage
    try:
        file_path = await upload_file(
            file_bytes=contents,
            original_filename=file.filename or "upload",
            company_id=str(user.company_id),
            subfolder=f"clients/{client.id}/documents",
        )
    except StorageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.detail) from exc

    # Create record in dedicated table
    doc = ClientDocument(
        company_id=user.company_id,
        client_id=client.id,
        document_type=DocumentType(document_type),
        file_name=file.filename or "upload",
        file_path=file_path,
        file_size=len(contents),
        description=description,
        status=DocumentStatus.PENDING_REVIEW,
    )
    db.add(doc)
    await db.flush()

    return _enrich_response(doc)


@router.get("/{document_id}", response_model=ClientDocumentResponse)
async def get_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Get details of a specific document."""
    client = await _get_client(db, user)

    row = await db.execute(
        select(ClientDocument).where(
            ClientDocument.id == document_id,
            ClientDocument.client_id == client.id,
            ClientDocument.company_id == user.company_id,
        )
    )
    doc = row.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return _enrich_response(doc)


@router.get("/{document_id}/download")
async def download_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Redirect to the public URL for document download."""
    client = await _get_client(db, user)

    row = await db.execute(
        select(ClientDocument).where(
            ClientDocument.id == document_id,
            ClientDocument.client_id == client.id,
            ClientDocument.company_id == user.company_id,
        )
    )
    doc = row.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        url = get_public_url(doc.file_path)
    except Exception:
        raise HTTPException(status_code=404, detail="File not available in storage")

    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=url)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Delete a document (only if still PENDING_REVIEW)."""
    client = await _get_client(db, user)

    row = await db.execute(
        select(ClientDocument).where(
            ClientDocument.id == document_id,
            ClientDocument.client_id == client.id,
            ClientDocument.company_id == user.company_id,
        )
    )
    doc = row.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.status != DocumentStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only documents with PENDING_REVIEW status can be deleted",
        )

    # Remove from storage
    try:
        await delete_file(doc.file_path)
    except StorageError:
        pass  # File may already be deleted

    await db.delete(doc)
    await db.flush()
    return None
