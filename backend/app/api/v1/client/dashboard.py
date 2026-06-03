
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
from app.models.development import Development
from app.models.enums import InvoiceStatus
from app.models.invoice import Invoice
from app.models.lot import Lot
from app.models.user import Profile
from app.schemas.dashboard import ClientSummary, RecentActivity
from app.schemas.lot import ClientLotResponse
from app.services.storage_service import enrich_photos

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
    client_lots = rows.scalars().all()

    # Preload lots + developments to attach the photos the admin exposed.
    lot_ids = [cl.lot_id for cl in client_lots]
    lots_by_id: dict = {}
    devs_by_id: dict = {}
    if lot_ids:
        lot_rows = await db.execute(select(Lot).where(Lot.id.in_(lot_ids)))
        lots_by_id = {lot.id: lot for lot in lot_rows.scalars().all()}
        dev_ids = {lot.development_id for lot in lots_by_id.values()}
        if dev_ids:
            dev_rows = await db.execute(select(Development).where(Development.id.in_(dev_ids)))
            devs_by_id = {dev.id: dev for dev in dev_rows.scalars().all()}

    result = []
    for cl in client_lots:
        data = ClientLotResponse.model_validate(cl).model_dump()
        lot = lots_by_id.get(cl.lot_id)
        if lot:
            dev = devs_by_id.get(lot.development_id)
            data["lot_number"] = lot.lot_number
            data["block"] = lot.block
            data["development_name"] = dev.name if dev else None
            data["lot_photos"] = enrich_photos(lot.photos or [], only_visible=True)
            data["development_photos"] = enrich_photos(dev.photos or [], only_visible=True) if dev else []
        result.append(data)
    return result


@router.get("/recent-activity", response_model=list[RecentActivity])
async def recent_activity(
    limit: int = Query(10, ge=1, le=50),
    user: Profile = Depends(get_client_user),
):
    """Placeholder – returns empty list until activity tracking is wired."""
    return []
