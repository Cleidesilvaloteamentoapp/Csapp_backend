"""Client portal dashboard endpoints."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_client_user
from app.models.client import Client
from app.models.client_lot import ClientLot
from app.models.enums import InvoiceStatus
from app.models.invoice import Invoice
from app.models.user import Profile
from app.schemas.dashboard import ClientSummary, RecentActivity
from app.schemas.lot import ClientLotResponse

router = APIRouter(prefix="/dashboard", tags=["Client Dashboard"])


def _get_client_filter(profile: Profile):
    """Return the profile_id to filter client data."""
    return profile.id


@router.get("/summary", response_model=ClientSummary)
async def client_summary(
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Summary for the client portal."""
    client_row = await db.execute(
        select(Client).where(Client.profile_id == user.id, Client.company_id == user.company_id)
    )
    client = client_row.scalar_one_or_none()
    if not client:
        return ClientSummary()

    lots_count = 0
    next_due_date = None
    next_due_amount = None
    pending = 0
    overdue = 0

    cl_rows = await db.execute(
        select(ClientLot).where(ClientLot.client_id == client.id)
    )
    client_lots = cl_rows.scalars().all()
    lots_count = len(client_lots)

    for cl in client_lots:
        inv_rows = await db.execute(
            select(Invoice).where(Invoice.client_lot_id == cl.id)
        )
        for inv in inv_rows.scalars().all():
            if inv.status == InvoiceStatus.PENDING:
                pending += 1
                if next_due_date is None or inv.due_date < next_due_date:
                    next_due_date = inv.due_date
                    next_due_amount = inv.amount
            elif inv.status == InvoiceStatus.OVERDUE:
                overdue += 1

    return ClientSummary(
        total_lots=lots_count,
        next_due_date=next_due_date,
        next_due_amount=next_due_amount,
        pending_invoices=pending,
        overdue_invoices=overdue,
    )


@router.get("/my-lots", response_model=list[ClientLotResponse])
async def my_lots(
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """List lots owned by the current client."""
    client_row = await db.execute(
        select(Client).where(Client.profile_id == user.id, Client.company_id == user.company_id)
    )
    client = client_row.scalar_one_or_none()
    if not client:
        return []

    rows = await db.execute(
        select(ClientLot).where(ClientLot.client_id == client.id)
    )
    return [ClientLotResponse.model_validate(r) for r in rows.scalars().all()]


@router.get("/recent-activity", response_model=list[RecentActivity])
async def recent_activity(
    limit: int = Query(10, ge=1, le=50),
    user: Profile = Depends(get_client_user),
):
    """Placeholder – returns empty list until activity tracking is wired."""
    return []
