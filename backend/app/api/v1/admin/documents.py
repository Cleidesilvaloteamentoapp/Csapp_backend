from typing import Optional

"""Admin document review endpoints."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.database import get_db
from app.core.deps import get_company_admin, require_permission
from app.models.client_document import ClientDocument
from app.models.enums import DocumentStatus, DocumentType
from app.models.user import Profile
from app.schemas.client_document import (
    ClientDocumentResponse,
    ClientDocumentUpdate,
    DocumentReviewRequest,
)
from app.services.storage_service import get_public_url

router = APIRouter(prefix="/documents", tags=["Admin Documents"])


def _enrich(doc: ClientDocument) -> dict:
    resp = ClientDocumentResponse.model_validate(doc).model_dump()
    try:
        resp["file_url"] = get_public_url(doc.file_path)
    except Exception:
        resp["file_url"] = None
    return resp


@router.get("", response_model=list[ClientDocumentResponse])
async def list_documents(
    client_id: Optional[UUID] = None,
    doc_status: Optional[str] = None,
    document_type: Optional[str] = None,
    tag: Optional[str] = Query(default=None, description="Filter documents containing this tag"),
    page: int = 1,
    per_page: int = 50,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(require_permission("view_documents")),
):
    """List all client documents for the company (with filters)."""
    query = select(ClientDocument).where(ClientDocument.company_id == user.company_id)

    if client_id:
        query = query.where(ClientDocument.client_id == client_id)
    if doc_status:
        query = query.where(ClientDocument.status == doc_status)
    if document_type:
        query = query.where(ClientDocument.document_type == document_type)
    if tag:
        # Postgres array contains operator
        query = query.where(ClientDocument.tags.any(tag))

    query = query.order_by(ClientDocument.created_at.desc())
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    rows = await db.execute(query)
    return [_enrich(d) for d in rows.scalars().all()]


@router.get("/pending-count")
async def pending_count(
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(require_permission("view_documents")),
):
    """Count documents awaiting review."""
    row = await db.execute(
        select(func.count(ClientDocument.id)).where(
            ClientDocument.company_id == user.company_id,
            ClientDocument.status == DocumentStatus.PENDING_REVIEW,
        )
    )
    return {"pending_count": row.scalar() or 0}


@router.get("/{document_id}", response_model=ClientDocumentResponse)
async def get_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(require_permission("view_documents")),
):
    """Get a specific document by ID."""
    row = await db.execute(
        select(ClientDocument).where(
            ClientDocument.id == document_id,
            ClientDocument.company_id == user.company_id,
        )
    )
    doc = row.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return _enrich(doc)


@router.get("/{document_id}/download")
async def download_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(require_permission("view_documents")),
):
    """Return a signed URL redirect to download the document file."""
    row = await db.execute(
        select(ClientDocument).where(
            ClientDocument.id == document_id,
            ClientDocument.company_id == user.company_id,
        )
    )
    doc = row.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        url = get_public_url(doc.file_path)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha ao gerar URL de download: {exc}",
        )
    return RedirectResponse(url=url)


@router.patch("/{document_id}", response_model=ClientDocumentResponse)
async def update_document(
    document_id: UUID,
    body: ClientDocumentUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(require_permission("manage_documents")),
):
    """Update document category (document_type), description and/or tags."""
    row = await db.execute(
        select(ClientDocument).where(
            ClientDocument.id == document_id,
            ClientDocument.company_id == user.company_id,
        )
    )
    doc = row.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    changes: list[str] = []
    if body.document_type is not None:
        try:
            doc.document_type = DocumentType(body.document_type)
            changes.append(f"type={body.document_type}")
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"document_type inválido: {body.document_type}",
            )
    if body.description is not None:
        doc.description = body.description
        changes.append("description")
    if body.tags is not None:
        cleaned = [str(t).strip() for t in body.tags if str(t).strip()][:20]
        doc.tags = cleaned
        changes.append(f"tags={cleaned}")
    if body.visible_to_client is not None:
        doc.visible_to_client = body.visible_to_client
        changes.append(f"visible_to_client={body.visible_to_client}")

    if not changes:
        return _enrich(doc)

    await db.flush()

    await log_audit(
        db,
        user_id=user.id,
        company_id=user.company_id,
        table_name="client_documents",
        operation="UPDATE",
        resource_id=str(doc.id),
        detail=", ".join(changes),
        ip_address=request.client.host if request.client else None,
    )
    return _enrich(doc)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(require_permission("manage_documents")),
):
    """Delete a client document (also removes the file from storage)."""
    from app.services.storage_service import delete_file

    row = await db.execute(
        select(ClientDocument).where(
            ClientDocument.id == document_id,
            ClientDocument.company_id == user.company_id,
        )
    )
    doc = row.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = doc.file_path
    await db.delete(doc)
    await db.flush()

    try:
        await delete_file(file_path)
    except Exception:
        # File may have been removed already; row deletion is the source of truth
        pass

    await log_audit(
        db,
        user_id=user.id,
        company_id=user.company_id,
        table_name="client_documents",
        operation="DELETE",
        resource_id=str(document_id),
        detail=f"Deleted document {file_path}",
        ip_address=request.client.host if request.client else None,
    )
    return None


@router.patch("/{document_id}/review", response_model=ClientDocumentResponse)
async def review_document(
    document_id: UUID,
    body: DocumentReviewRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(require_permission("manage_documents")),
):
    """Approve or reject a client document."""
    row = await db.execute(
        select(ClientDocument).where(
            ClientDocument.id == document_id,
            ClientDocument.company_id == user.company_id,
        )
    )
    doc = row.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.status != DocumentStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document is already {doc.status.value}",
        )

    doc.status = DocumentStatus(body.status)
    doc.reviewed_by = user.id
    doc.reviewed_at = datetime.now(timezone.utc)
    if body.status == "REJECTED" and body.rejection_reason:
        doc.rejection_reason = body.rejection_reason

    await db.flush()

    await log_audit(
        db,
        user_id=user.id,
        company_id=user.company_id,
        table_name="client_documents",
        operation=f"DOCUMENT_{body.status}",
        resource_id=str(doc.id),
        detail=f"client_id={doc.client_id} type={doc.document_type.value}",
        ip_address=request.client.host if request.client else None,
    )

    return _enrich(doc)
