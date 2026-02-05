"""Client invoice (boleto) endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_client_user
from app.models.client import Client
from app.models.client_lot import ClientLot
from app.models.invoice import Invoice
from app.models.user import Profile
from app.schemas.invoice import InvoiceResponse

router = APIRouter(prefix="/invoices", tags=["Client Invoices"])


async def _get_client(db: AsyncSession, user: Profile) -> Client | None:
    """Retrieve the Client record linked to the current profile."""
    row = await db.execute(
        select(Client).where(Client.profile_id == user.id, Client.company_id == user.company_id)
    )
    return row.scalar_one_or_none()


@router.get("/", response_model=list[InvoiceResponse])
async def list_invoices(
    lot_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """List invoices for the current client."""
    client = await _get_client(db, user)
    if not client:
        return []

    base = (
        select(Invoice)
        .join(ClientLot, ClientLot.id == Invoice.client_lot_id)
        .where(ClientLot.client_id == client.id, Invoice.company_id == user.company_id)
    )
    if lot_id:
        base = base.where(ClientLot.lot_id == lot_id)

    rows = await db.execute(base.order_by(Invoice.due_date))
    return [InvoiceResponse.model_validate(r) for r in rows.scalars().all()]


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Get invoice details (with barcode and payment URL)."""
    client = await _get_client(db, user)
    if not client:
        raise HTTPException(status_code=404, detail="Client profile not found")

    row = await db.execute(
        select(Invoice)
        .join(ClientLot, ClientLot.id == Invoice.client_lot_id)
        .where(
            Invoice.id == invoice_id,
            ClientLot.client_id == client.id,
            Invoice.company_id == user.company_id,
        )
    )
    invoice = row.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    return InvoiceResponse.model_validate(invoice)


@router.get("/{invoice_id}/pdf")
async def download_invoice_pdf(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Redirect to the Asaas payment URL for PDF download."""
    client = await _get_client(db, user)
    if not client:
        raise HTTPException(status_code=404, detail="Client profile not found")

    row = await db.execute(
        select(Invoice)
        .join(ClientLot, ClientLot.id == Invoice.client_lot_id)
        .where(
            Invoice.id == invoice_id,
            ClientLot.client_id == client.id,
            Invoice.company_id == user.company_id,
        )
    )
    invoice = row.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if not invoice.payment_url:
        raise HTTPException(status_code=404, detail="PDF not available for this invoice")

    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=invoice.payment_url)
