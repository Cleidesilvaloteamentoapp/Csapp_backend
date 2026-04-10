from typing import Optional

"""Admin client management endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.database import get_db
from app.core.deps import get_company_admin, require_permission
from app.models.client_lot import ClientLot
from app.models.invoice import Invoice
from app.models.user import Profile
from app.schemas.client import ClientCreate, ClientResponse, ClientUpdate
from app.schemas.common import PaginatedResponse, PaginationParams
from app.schemas.invoice import InvoiceResponse
from app.schemas.lot import ClientLotResponse
from app.services import client_service
from app.services.storage_service import upload_file, get_public_url
from app.utils.exceptions import StorageError

router = APIRouter(prefix="/clients", tags=["Admin Clients"])


@router.get("/", response_model=PaginatedResponse[ClientResponse])
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


@router.post("/", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
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


@router.post("/{client_id}/documents", status_code=status.HTTP_201_CREATED)
async def upload_client_document(
    client_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_documents")),
):
    """Upload a document for a client."""
    client = await client_service.get_client(db, admin.company_id, client_id)

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

    docs = list(client.documents or [])
    docs.append(path)
    client.documents = docs
    await db.flush()

    return {"path": path, "url": get_public_url(path)}
