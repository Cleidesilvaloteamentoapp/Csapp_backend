from typing import Optional

"""Admin service type and service order endpoints."""

import math
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_company_admin, require_permission
from app.models.enums import ServiceOrderStatus
from app.models.service import ServiceOrder, ServiceType
from app.models.user import Profile
from app.schemas.common import PaginatedResponse
from app.schemas.service import (
    ServiceOrderFinancialUpdate,
    ServiceOrderResponse,
    ServiceOrderStatusUpdate,
    ServiceTypeCreate,
    ServiceTypeResponse,
    ServiceTypeUpdate,
)

router = APIRouter(prefix="/services", tags=["Admin Services"])


# ---------------------------------------------------------------------------
# Service Types
# ---------------------------------------------------------------------------


@router.get("/types", response_model=list[ServiceTypeResponse])
async def list_service_types(
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_financial")),
):
    """List service types for the company."""
    rows = await db.execute(
        select(ServiceType)
        .where(ServiceType.company_id == admin.company_id)
        .order_by(ServiceType.name)
    )
    return [ServiceTypeResponse.model_validate(s) for s in rows.scalars().all()]


@router.post("/types", response_model=ServiceTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_service_type(
    data: ServiceTypeCreate,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_financial")),
):
    """Create a new service type."""
    st = ServiceType(company_id=admin.company_id, **data.model_dump())
    db.add(st)
    await db.flush()
    return ServiceTypeResponse.model_validate(st)


@router.put("/types/{type_id}", response_model=ServiceTypeResponse)
async def update_service_type(
    type_id: UUID,
    data: ServiceTypeUpdate,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_financial")),
):
    """Update a service type."""
    result = await db.execute(
        select(ServiceType).where(
            ServiceType.id == type_id, ServiceType.company_id == admin.company_id
        )
    )
    st = result.scalar_one_or_none()
    if not st:
        raise HTTPException(status_code=404, detail="Service type not found")

    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(st, k, v)
    await db.flush()
    return ServiceTypeResponse.model_validate(st)


# ---------------------------------------------------------------------------
# Service Orders
# ---------------------------------------------------------------------------


@router.get("/orders", response_model=PaginatedResponse[ServiceOrderResponse])
async def list_orders(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    status_filter: Optional[str] = Query(None, alias="status"),
    client_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_financial")),
):
    """List service orders with filters."""
    base = select(ServiceOrder).where(ServiceOrder.company_id == admin.company_id)
    if status_filter:
        base = base.where(ServiceOrder.status == status_filter)
    if client_id:
        base = base.where(ServiceOrder.client_id == client_id)

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
    rows = await db.execute(
        base.order_by(ServiceOrder.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    items = [ServiceOrderResponse.model_validate(r) for r in rows.scalars().all()]

    return PaginatedResponse[ServiceOrderResponse](
        items=items, total=total, page=page, per_page=per_page,
        pages=math.ceil(total / per_page) if per_page else 0,
    )


@router.get("/orders/{order_id}", response_model=ServiceOrderResponse)
async def get_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_financial")),
):
    """Get service order details."""
    result = await db.execute(
        select(ServiceOrder).where(
            ServiceOrder.id == order_id, ServiceOrder.company_id == admin.company_id
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Service order not found")
    return ServiceOrderResponse.model_validate(order)


@router.patch("/orders/{order_id}/status", response_model=ServiceOrderResponse)
async def update_order_status(
    order_id: UUID,
    data: ServiceOrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_financial")),
):
    """Update the status of a service order."""
    result = await db.execute(
        select(ServiceOrder).where(
            ServiceOrder.id == order_id, ServiceOrder.company_id == admin.company_id
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Service order not found")

    order.status = ServiceOrderStatus(data.status)
    if data.status == "completed":
        order.execution_date = date.today()
    await db.flush()
    return ServiceOrderResponse.model_validate(order)


@router.patch("/orders/{order_id}/financial", response_model=ServiceOrderResponse)
async def update_order_financial(
    order_id: UUID,
    data: ServiceOrderFinancialUpdate,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_financial")),
):
    """Update cost / revenue of a service order."""
    result = await db.execute(
        select(ServiceOrder).where(
            ServiceOrder.id == order_id, ServiceOrder.company_id == admin.company_id
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Service order not found")

    if data.cost is not None:
        order.cost = data.cost
    if data.revenue is not None:
        order.revenue = data.revenue
    await db.flush()
    return ServiceOrderResponse.model_validate(order)


@router.get("/analytics")
async def service_analytics(
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_financial")),
):
    """Cost vs revenue analysis for services."""
    cid = admin.company_id
    q = (
        select(
            ServiceType.name,
            func.coalesce(func.sum(ServiceOrder.cost), 0).label("total_cost"),
            func.coalesce(func.sum(ServiceOrder.revenue), 0).label("total_revenue"),
            func.count(ServiceOrder.id).label("count"),
        )
        .join(ServiceOrder, ServiceOrder.service_type_id == ServiceType.id)
        .where(ServiceType.company_id == cid)
        .group_by(ServiceType.name)
    )
    rows = (await db.execute(q)).all()
    return [
        {
            "service_name": r.name,
            "total_cost": float(r.total_cost),
            "total_revenue": float(r.total_revenue),
            "profit": float(r.total_revenue) - float(r.total_cost),
            "order_count": r.count,
        }
        for r in rows
    ]
