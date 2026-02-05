"""Client service order endpoints."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_client_user
from app.models.client import Client
from app.models.enums import ServiceOrderStatus
from app.models.service import ServiceOrder, ServiceType
from app.models.user import Profile
from app.schemas.service import (
    ServiceOrderCreate,
    ServiceOrderResponse,
    ServiceTypeResponse,
)

router = APIRouter(prefix="/services", tags=["Client Services"])


async def _get_client(db: AsyncSession, user: Profile) -> Client | None:
    row = await db.execute(
        select(Client).where(Client.profile_id == user.id, Client.company_id == user.company_id)
    )
    return row.scalar_one_or_none()


@router.get("/types", response_model=list[ServiceTypeResponse])
async def list_available_services(
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """List active service types available to the client."""
    rows = await db.execute(
        select(ServiceType).where(
            ServiceType.company_id == user.company_id,
            ServiceType.is_active.is_(True),
        )
    )
    return [ServiceTypeResponse.model_validate(s) for s in rows.scalars().all()]


@router.post("/orders", response_model=ServiceOrderResponse, status_code=status.HTTP_201_CREATED)
async def request_service(
    data: ServiceOrderCreate,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Client requests a service."""
    client = await _get_client(db, user)
    if not client:
        raise HTTPException(status_code=404, detail="Client profile not found")

    # Validate service type
    st = (await db.execute(
        select(ServiceType).where(
            ServiceType.id == data.service_type_id,
            ServiceType.company_id == user.company_id,
            ServiceType.is_active.is_(True),
        )
    )).scalar_one_or_none()
    if not st:
        raise HTTPException(status_code=404, detail="Service type not found or inactive")

    order = ServiceOrder(
        company_id=user.company_id,
        client_id=client.id,
        lot_id=data.lot_id,
        service_type_id=data.service_type_id,
        requested_date=date.today(),
        status=ServiceOrderStatus.REQUESTED,
        notes=data.notes,
    )
    db.add(order)
    await db.flush()
    return ServiceOrderResponse.model_validate(order)


@router.get("/orders", response_model=list[ServiceOrderResponse])
async def my_orders(
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """List service orders for the current client."""
    client = await _get_client(db, user)
    if not client:
        return []

    rows = await db.execute(
        select(ServiceOrder)
        .where(ServiceOrder.client_id == client.id, ServiceOrder.company_id == user.company_id)
        .order_by(ServiceOrder.created_at.desc())
    )
    return [ServiceOrderResponse.model_validate(r) for r in rows.scalars().all()]


@router.get("/orders/{order_id}", response_model=ServiceOrderResponse)
async def get_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Get service order details."""
    client = await _get_client(db, user)
    if not client:
        raise HTTPException(status_code=404, detail="Client profile not found")

    row = await db.execute(
        select(ServiceOrder).where(
            ServiceOrder.id == order_id,
            ServiceOrder.client_id == client.id,
            ServiceOrder.company_id == user.company_id,
        )
    )
    order = row.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Service order not found")
    return ServiceOrderResponse.model_validate(order)
