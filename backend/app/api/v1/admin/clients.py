from typing import Optional

"""Admin client management endpoints."""

import json
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile, File, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel, EmailStr, Field

from app.core.audit import log_audit
from app.core.database import get_db
from app.core.deps import get_company_admin, require_permission
from app.core.security import hash_password
from app.models.client import Client
from app.models.client_document import ClientDocument
from app.models.client_lot import ClientLot
from app.models.enums import DocumentStatus, DocumentType, UserRole
from app.models.invoice import Invoice
from app.models.user import Profile
from app.schemas.client import ClientCreate, ClientResponse, ClientUpdate
from app.schemas.client_document import ClientDocumentResponse
from app.schemas.common import PaginatedResponse, PaginationParams
from app.schemas.invoice import InvoiceResponse
from app.schemas.lot import ClientLotResponse
from app.services import client_service
from app.services.email_service import send_credentials_email
from app.services.storage_service import upload_file, get_public_url
from app.utils.exceptions import StorageError

router = APIRouter(prefix="/clients", tags=["Admin Clients"])


class PortalAccessCreate(BaseModel):
    """Payload to create portal access for an existing client."""

    password: str = Field(..., min_length=8, max_length=128)
    send_email: bool = Field(
        default=True, description="If true, email the client their credentials."
    )


class PortalPasswordUpdate(BaseModel):
    """Payload to reset the portal password for an existing client."""

    password: str = Field(..., min_length=8, max_length=128)


class PortalAccessStatus(BaseModel):
    has_access: bool
    profile_id: Optional[UUID] = None


@router.get("", response_model=PaginatedResponse[ClientResponse])
async def list_clients(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_clients")),
):
    """List clients with pagination and filters."""
    params = PaginationParams(page=page, per_page=per_page)
    return await client_service.list_clients(
        db, admin.company_id, params, status_filter=status_filter, search=search
    )


@router.post("", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    data: ClientCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_clients")),
):
    """Create a new client."""
    client = await client_service.create_client(db, admin.company_id, admin.id, data)

    await log_audit(
        db, user_id=admin.id, company_id=admin.company_id,
        table_name="clients", operation="CREATE",
        resource_id=str(client.id), detail=f"Created client {client.full_name}",
        ip_address=request.client.host if request.client else None,
    )

    return ClientResponse.model_validate(client)


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_clients")),
):
    """Get client details."""
    client = await client_service.get_client(db, admin.company_id, client_id)
    return ClientResponse.model_validate(client)


@router.put("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: UUID,
    data: ClientUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_clients")),
):
    """Update client data."""
    client = await client_service.update_client(db, admin.company_id, client_id, data)
    await log_audit(
        db, user_id=admin.id, company_id=admin.company_id,
        table_name="clients", operation="UPDATE",
        resource_id=str(client_id),
        detail=f"Updated fields: {[k for k,v in data.model_dump(exclude_unset=True).items()]}",
        ip_address=request.client.host if request.client else None,
    )
    return ClientResponse.model_validate(client)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_clients")),
):
    """Deactivate (soft-delete) a client."""
    await client_service.deactivate_client(db, admin.company_id, client_id)
    await log_audit(
        db, user_id=admin.id, company_id=admin.company_id,
        table_name="clients", operation="DELETE",
        resource_id=str(client_id), detail="Client deactivated",
        ip_address=request.client.host if request.client else None,
    )
    return None


@router.get("/{client_id}/lots", response_model=list[ClientLotResponse])
async def get_client_lots(
    client_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_clients")),
):
    """List lots belonging to a client."""
    # Ensure client belongs to this company
    await client_service.get_client(db, admin.company_id, client_id)
    rows = await db.execute(
        select(ClientLot).where(
            ClientLot.client_id == client_id,
            ClientLot.company_id == admin.company_id,
        )
    )
    return [ClientLotResponse.model_validate(r) for r in rows.scalars().all()]


@router.get("/{client_id}/invoices", response_model=list[InvoiceResponse])
async def get_client_invoices(
    client_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_financial")),
):
    """List invoices for a client (via their client_lots)."""
    await client_service.get_client(db, admin.company_id, client_id)
    rows = await db.execute(
        select(Invoice)
        .join(ClientLot, ClientLot.id == Invoice.client_lot_id)
        .where(
            ClientLot.client_id == client_id,
            Invoice.company_id == admin.company_id,
        )
        .order_by(Invoice.due_date)
    )
    return [InvoiceResponse.model_validate(r) for r in rows.scalars().all()]


@router.get("/{client_id}/documents", response_model=list[str])
async def get_client_documents(
    client_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_documents")),
):
    """List document URLs for a client."""
    client = await client_service.get_client(db, admin.company_id, client_id)
    docs = client.documents or []
    return [get_public_url(d) if isinstance(d, str) else d for d in docs]


@router.post(
    "/{client_id}/documents",
    response_model=ClientDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_client_document(
    client_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    document_type: str = Form("OUTROS"),
    description: Optional[str] = Form(default=None),
    tags: Optional[str] = Form(
        default=None, description="JSON array of tag strings, e.g. '[\"urgente\"]'"
    ),
    visible_to_client: bool = Form(
        default=False, description="Expor o documento ao cliente no portal"
    ),
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_documents")),
):
    """Upload a document for a client. Creates a ClientDocument row."""
    client = await client_service.get_client(db, admin.company_id, client_id)

    # Validate document_type against the enum
    try:
        doc_type_enum = DocumentType(document_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"document_type inválido: {document_type}",
        )

    # Parse tags (may arrive as JSON string in multipart form)
    parsed_tags: list[str] = []
    if tags:
        try:
            decoded = json.loads(tags)
            if isinstance(decoded, list):
                parsed_tags = [str(t).strip() for t in decoded if str(t).strip()]
        except json.JSONDecodeError:
            # Fall back: comma-separated string
            parsed_tags = [t.strip() for t in tags.split(",") if t.strip()]
    parsed_tags = parsed_tags[:20]

    try:
        contents = await file.read()
        path = await upload_file(
            file_bytes=contents,
            original_filename=file.filename or "upload",
            company_id=str(admin.company_id),
            subfolder=f"clients/{client_id}/documents",
        )
    except StorageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.detail) from exc

    doc = ClientDocument(
        company_id=admin.company_id,
        client_id=client.id,
        document_type=doc_type_enum,
        file_name=file.filename or "upload",
        file_path=path,
        file_size=len(contents),
        description=description,
        tags=parsed_tags,
        visible_to_client=visible_to_client,
        status=DocumentStatus.PENDING_REVIEW,
    )
    db.add(doc)
    await db.flush()

    await log_audit(
        db,
        user_id=admin.id,
        company_id=admin.company_id,
        table_name="client_documents",
        operation="CREATE",
        resource_id=str(doc.id),
        detail=f"Uploaded {file.filename} ({doc_type_enum.value}) for client {client.full_name}",
        ip_address=request.client.host if request.client else None,
    )

    payload = ClientDocumentResponse.model_validate(doc).model_dump()
    try:
        payload["file_url"] = get_public_url(doc.file_path)
    except Exception:
        payload["file_url"] = None
    return payload


# ---------------------------------------------------------------------------
# Portal access management
# ---------------------------------------------------------------------------

@router.get("/{client_id}/portal-access", response_model=PortalAccessStatus)
async def get_portal_access_status(
    client_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_clients")),
):
    """Whether this client already has portal access (a linked profile)."""
    client = await client_service.get_client(db, admin.company_id, client_id)
    return PortalAccessStatus(
        has_access=client.profile_id is not None,
        profile_id=client.profile_id,
    )


@router.post(
    "/{client_id}/portal-access",
    response_model=PortalAccessStatus,
    status_code=status.HTTP_201_CREATED,
)
async def create_portal_access(
    client_id: UUID,
    body: PortalAccessCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_clients")),
):
    """Create portal credentials for an existing client.

    Creates a Profile with role=CLIENT, links it to the client, and optionally
    emails the temporary password.
    """
    client = await client_service.get_client(db, admin.company_id, client_id)
    if client.profile_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cliente já possui acesso ao portal. Use PATCH para resetar a senha.",
        )

    profile = Profile(
        company_id=admin.company_id,
        role=UserRole.CLIENT,
        full_name=client.full_name,
        email=client.email,
        cpf_cnpj=client.cpf_cnpj,
        phone=client.phone,
        hashed_password=hash_password(body.password),
    )
    db.add(profile)
    try:
        await db.flush()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Não foi possível criar o acesso: {exc}",
        )
    client.profile_id = profile.id
    await db.flush()

    await log_audit(
        db,
        user_id=admin.id,
        company_id=admin.company_id,
        table_name="profiles",
        operation="CREATE_PORTAL_ACCESS",
        resource_id=str(profile.id),
        detail=f"Created portal access for client {client.full_name}",
        ip_address=request.client.host if request.client else None,
    )

    if body.send_email:
        try:
            await send_credentials_email(
                to=client.email, name=client.full_name, temp_password=body.password
            )
        except Exception:
            # Email failure must not roll back the access creation
            pass

    return PortalAccessStatus(has_access=True, profile_id=profile.id)


@router.patch("/{client_id}/portal-password", response_model=PortalAccessStatus)
async def reset_portal_password(
    client_id: UUID,
    body: PortalPasswordUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_clients")),
):
    """Reset the portal password for a client (administrative action)."""
    client = await client_service.get_client(db, admin.company_id, client_id)
    if not client.profile_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente não possui acesso ao portal. Use POST para criar.",
        )

    row = await db.execute(
        select(Profile).where(
            Profile.id == client.profile_id,
            Profile.company_id == admin.company_id,
        )
    )
    profile = row.scalar_one_or_none()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perfil vinculado não encontrado.",
        )

    profile.hashed_password = hash_password(body.password)
    await db.flush()

    await log_audit(
        db,
        user_id=admin.id,
        company_id=admin.company_id,
        table_name="profiles",
        operation="RESET_PORTAL_PASSWORD",
        resource_id=str(profile.id),
        detail=f"Reset password for client {client.full_name}",
        ip_address=request.client.host if request.client else None,
    )

    return PortalAccessStatus(has_access=True, profile_id=profile.id)
