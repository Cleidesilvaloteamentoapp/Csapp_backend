from typing import Optional

"""Admin financial endpoints."""

import math
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_company_admin
from app.models.client import Client
from app.models.client_lot import ClientLot
from app.models.enums import InvoiceStatus
from app.models.invoice import Invoice
from app.models.service import ServiceOrder, ServiceType
from app.models.user import Profile
from app.schemas.common import PaginatedResponse
from app.schemas.dashboard import DefaulterInfo, FinancialOverview, RevenueByService
from app.schemas.invoice import InvoiceResponse

router = APIRouter(prefix="/financial", tags=["Admin Financial"])


@router.get("/summary", response_model=FinancialOverview)
async def financial_summary(
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Complete financial summary."""
    cid = admin.company_id

    receivable = (await db.execute(
        select(func.coalesce(func.sum(Invoice.amount), 0)).where(
            Invoice.company_id == cid, Invoice.status == InvoiceStatus.PENDING
        )
    )).scalar()

    received = (await db.execute(
        select(func.coalesce(func.sum(Invoice.amount), 0)).where(
            Invoice.company_id == cid, Invoice.status == InvoiceStatus.PAID
        )
    )).scalar()

    overdue_sum, overdue_cnt = (await db.execute(
        select(
            func.coalesce(func.sum(Invoice.amount), 0),
            func.count(),
        ).where(Invoice.company_id == cid, Invoice.status == InvoiceStatus.OVERDUE)
    )).one()

    return FinancialOverview(
        total_receivable=Decimal(str(receivable)),
        total_received=Decimal(str(received)),
        total_overdue=Decimal(str(overdue_sum)),
        overdue_count=overdue_cnt,
    )


@router.get("/receivables", response_model=PaginatedResponse[InvoiceResponse])
async def receivables(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Paginated list of invoices (accounts receivable)."""
    cid = admin.company_id
    base = select(Invoice).where(Invoice.company_id == cid)
    if status_filter:
        base = base.where(Invoice.status == status_filter)

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
    rows = await db.execute(
        base.order_by(Invoice.due_date).offset((page - 1) * per_page).limit(per_page)
    )
    items = [InvoiceResponse.model_validate(r) for r in rows.scalars().all()]

    return PaginatedResponse[InvoiceResponse](
        items=items, total=total, page=page, per_page=per_page,
        pages=math.ceil(total / per_page) if per_page else 0,
    )


@router.get("/defaulters", response_model=list[DefaulterInfo])
async def defaulters(
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """List defaulting clients with overdue months and amounts."""
    cid = admin.company_id
    today = date.today()

    q = (
        select(
            Client.id,
            Client.full_name,
            func.count(Invoice.id).label("overdue_count"),
            func.coalesce(func.sum(Invoice.amount), 0).label("overdue_amount"),
            func.min(Invoice.due_date).label("oldest_due"),
        )
        .join(ClientLot, ClientLot.client_id == Client.id)
        .join(Invoice, Invoice.client_lot_id == ClientLot.id)
        .where(
            Client.company_id == cid,
            Invoice.status == InvoiceStatus.OVERDUE,
        )
        .group_by(Client.id, Client.full_name)
        .order_by(func.min(Invoice.due_date))
    )
    rows = (await db.execute(q)).all()

    results = []
    for row in rows:
        oldest: date = row.oldest_due
        months_overdue = max(1, (today.year - oldest.year) * 12 + today.month - oldest.month)
        results.append(
            DefaulterInfo(
                client_id=row.id,
                client_name=row.full_name,
                overdue_months=months_overdue,
                overdue_amount=Decimal(str(row.overdue_amount)),
            )
        )
    return results


@router.get("/revenue-by-services", response_model=list[RevenueByService])
async def revenue_by_services(
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Revenue grouped by service type."""
    cid = admin.company_id
    q = (
        select(
            ServiceType.id,
            ServiceType.name,
            func.coalesce(func.sum(ServiceOrder.revenue), 0).label("total_revenue"),
            func.coalesce(func.sum(ServiceOrder.cost), 0).label("total_cost"),
            func.count(ServiceOrder.id).label("order_count"),
        )
        .join(ServiceOrder, ServiceOrder.service_type_id == ServiceType.id)
        .where(ServiceType.company_id == cid)
        .group_by(ServiceType.id, ServiceType.name)
    )
    rows = (await db.execute(q)).all()
    return [
        RevenueByService(
            service_type_id=r.id,
            service_name=r.name,
            total_revenue=Decimal(str(r.total_revenue)),
            total_cost=Decimal(str(r.total_cost)),
            order_count=r.order_count,
        )
        for r in rows
    ]
