from typing import Optional

"""Admin lot and development management endpoints."""

import math
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.database import get_db
from app.core.deps import get_company_admin, require_permission
from app.models.client import Client
from app.models.client_lot import ClientLot
from app.models.development import Development
from app.models.enums import AdjustmentFrequency, AdjustmentIndex, ClientLotStatus, InvoiceStatus, LotStatus, PropertyType
from app.models.invoice import Invoice
from app.models.lot import Lot
from app.models.user import Profile
from app.schemas.common import PaginatedResponse
from app.services import client_lot_service
from app.services.client_lot_service import get_remaining_installments, should_generate_next_batch
from app.schemas.financial_settings import ClientLotFinancialUpdate
from app.schemas.lot import (
    ClientLotResponse,
    DevelopmentCreate,
    DevelopmentFilter,
    DevelopmentResponse,
    DevelopmentUpdate,
    LotAssignRequest,
    LotCreate,
    LotResponse,
    LotUpdate,
)

router = APIRouter(prefix="/lots", tags=["Admin Lots"])
dev_router = APIRouter(prefix="/developments", tags=["Admin Developments"])


# ---------------------------------------------------------------------------
# Developments
# ---------------------------------------------------------------------------


@dev_router.get("", response_model=list[DevelopmentResponse])
async def list_developments(
    property_type: Optional[PropertyType] = Query(None, description="Filter by property type"),
    name: Optional[str] = Query(None, description="Filter by name (partial match)"),
    location: Optional[str] = Query(None, description="Filter by location (partial match)"),
    min_price: Optional[Decimal] = Query(None, ge=0, description="Minimum price"),
    max_price: Optional[Decimal] = Query(None, ge=0, description="Maximum price"),
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_lots")),
):
    """List developments for the current company with optional filters."""
    query = select(Development).where(Development.company_id == admin.company_id)

    # Apply filters
    if property_type:
        query = query.where(Development.property_type == property_type)
    if name:
        query = query.where(Development.name.ilike(f"%{name}%"))
    if location:
        query = query.where(Development.location.ilike(f"%{location}%"))
    if min_price is not None:
        query = query.where(Development.price >= min_price)
    if max_price is not None:
        query = query.where(Development.price <= max_price)

    query = query.order_by(Development.created_at.desc())
    rows = await db.execute(query)
    return [DevelopmentResponse.model_validate(d) for d in rows.scalars().all()]


def _validate_development_data(data: DevelopmentCreate | DevelopmentUpdate, is_update: bool = False) -> None:
    """Validate development data based on property type."""
    errors = []

    # Get property type, handling both create and update scenarios
    if hasattr(data, 'property_type') and data.property_type is not None:
        property_type = data.property_type
    elif is_update:
        return  # Skip validation on partial update if property_type not provided
    else:
        property_type = PropertyType.LOT

    # Lot-specific validations
    if property_type == PropertyType.LOT:
        if not is_update or hasattr(data, 'lot_number') and data.lot_number is not None:
            if not data.lot_number:
                errors.append("Número do lote é obrigatório para lotes")
        if not is_update or hasattr(data, 'area_m2') and data.area_m2 is not None:
            if not data.area_m2:
                errors.append("Área é obrigatória para lotes")

    # Residential validations (House/Apartment)
    elif property_type in [PropertyType.HOUSE, PropertyType.APARTMENT]:
        if not is_update or hasattr(data, 'bedrooms') and data.bedrooms is not None:
            if not data.bedrooms:
                errors.append("Número de quartos é obrigatório para imóveis residenciais")
        if not is_update or hasattr(data, 'bathrooms') and data.bathrooms is not None:
            if not data.bathrooms:
                errors.append("Número de banheiros é obrigatório para imóveis residenciais")
        if not is_update or hasattr(data, 'construction_area_m2') and data.construction_area_m2 is not None:
            if not data.construction_area_m2:
                errors.append("Área construída é obrigatória para imóveis residenciais")

    # Commercial validations
    elif property_type == PropertyType.COMMERCIAL:
        if not is_update or hasattr(data, 'construction_area_m2') and data.construction_area_m2 is not None:
            if not data.construction_area_m2:
                errors.append("Área construída é obrigatória para imóveis comerciais")

    # Rural validations
    elif property_type == PropertyType.RURAL:
        if not is_update or hasattr(data, 'area_m2') and data.area_m2 is not None:
            if not data.area_m2:
                errors.append("Área total é obrigatória para imóveis rurais")

    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))


@dev_router.post("", response_model=DevelopmentResponse, status_code=status.HTTP_201_CREATED)
async def create_development(
    data: DevelopmentCreate,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_lots")),
):
    """Create a new development."""
    _validate_development_data(data)
    dev = Development(company_id=admin.company_id, **data.model_dump())
    db.add(dev)
    await db.flush()
    return DevelopmentResponse.model_validate(dev)


@dev_router.get("/{dev_id}", response_model=DevelopmentResponse)
async def get_development(
    dev_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_lots")),
):
    """Get development details."""
    result = await db.execute(
        select(Development).where(
            Development.id == dev_id, Development.company_id == admin.company_id
        )
    )
    dev = result.scalar_one_or_none()
    if not dev:
        raise HTTPException(status_code=404, detail="Development not found")
    return DevelopmentResponse.model_validate(dev)


@dev_router.put("/{dev_id}", response_model=DevelopmentResponse)
async def update_development(
    dev_id: UUID,
    data: DevelopmentUpdate,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_lots")),
):
    """Update a development."""
    result = await db.execute(
        select(Development).where(
            Development.id == dev_id, Development.company_id == admin.company_id
        )
    )
    dev = result.scalar_one_or_none()
    if not dev:
        raise HTTPException(status_code=404, detail="Development not found")

    _validate_development_data(data, is_update=True)

    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(dev, k, v)
    await db.flush()
    return DevelopmentResponse.model_validate(dev)


# ---------------------------------------------------------------------------
# Lots
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[LotResponse])
async def list_lots(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    development_id: Optional[UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_lots")),
):
    """List lots with pagination and filters."""
    base = select(Lot).where(Lot.company_id == admin.company_id)
    if development_id:
        base = base.where(Lot.development_id == development_id)
    if status_filter:
        base = base.where(Lot.status == status_filter)

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
    rows = await db.execute(
        base.order_by(Lot.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    )
    items = [LotResponse.model_validate(r) for r in rows.scalars().all()]

    return PaginatedResponse[LotResponse](
        items=items, total=total, page=page, per_page=per_page,
        pages=math.ceil(total / per_page) if per_page else 0,
    )


@router.post("", response_model=LotResponse, status_code=status.HTTP_201_CREATED)
async def create_lot(
    data: LotCreate,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_lots")),
):
    """Create a new lot."""
    # Validate development belongs to company
    dev = (await db.execute(
        select(Development).where(
            Development.id == data.development_id,
            Development.company_id == admin.company_id,
        )
    )).scalar_one_or_none()
    if not dev:
        raise HTTPException(status_code=404, detail="Development not found in this company")

    lot = Lot(company_id=admin.company_id, **data.model_dump())
    db.add(lot)
    await db.flush()
    return LotResponse.model_validate(lot)


@router.get("/{lot_id}", response_model=LotResponse)
async def get_lot(
    lot_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_lots")),
):
    """Get lot details."""
    result = await db.execute(
        select(Lot).where(Lot.id == lot_id, Lot.company_id == admin.company_id)
    )
    lot = result.scalar_one_or_none()
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")
    return LotResponse.model_validate(lot)


@router.put("/{lot_id}", response_model=LotResponse)
async def update_lot(
    lot_id: UUID,
    data: LotUpdate,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_lots")),
):
    """Update a lot."""
    result = await db.execute(
        select(Lot).where(Lot.id == lot_id, Lot.company_id == admin.company_id)
    )
    lot = result.scalar_one_or_none()
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")

    for k, v in data.model_dump(exclude_unset=True).items():
        if k == "status":
            v = LotStatus(v)
        setattr(lot, k, v)
    await db.flush()
    return LotResponse.model_validate(lot)


@router.post("/assign", response_model=ClientLotResponse, status_code=status.HTTP_201_CREATED)
async def assign_lot(
    data: LotAssignRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_lots")),
):
    """Assign a lot to a client: creates client_lot + generates invoices."""
    cid = admin.company_id

    # Validate lot
    lot = (await db.execute(
        select(Lot).where(Lot.id == data.lot_id, Lot.company_id == cid)
    )).scalar_one_or_none()
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")
    if lot.status != LotStatus.AVAILABLE:
        raise HTTPException(status_code=400, detail="Lot is not available")

    # Validate client
    client = (await db.execute(
        select(Client).where(Client.id == data.client_id, Client.company_id == cid)
    )).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Calculate installment value considering down payment
    plan = data.payment_plan or {}
    num_installments = data.total_installments or int(plan.get("installments", 1))
    down_payment = data.down_payment or Decimal("0")
    financed_value = data.total_value - down_payment
    installment_value = financed_value / num_installments if num_installments > 0 else financed_value

    # Load company financial defaults for fields not provided in the request
    from app.models.company_financial_settings import CompanyFinancialSettings
    cfs_row = await db.execute(
        select(CompanyFinancialSettings).where(CompanyFinancialSettings.company_id == cid)
    )
    cfs = cfs_row.scalar_one_or_none()

    # Resolve per-lot values: request → company defaults → hardcoded
    penalty_rate = data.penalty_rate
    if penalty_rate is None and cfs:
        penalty_rate = cfs.penalty_rate

    daily_interest_rate = data.daily_interest_rate
    if daily_interest_rate is None and cfs:
        daily_interest_rate = cfs.daily_interest_rate

    adj_index = data.adjustment_index
    if adj_index is None and cfs:
        adj_index = cfs.adjustment_index.value if cfs.adjustment_index else None
    adj_index_enum = AdjustmentIndex(adj_index) if adj_index else None

    adj_freq = data.adjustment_frequency
    if adj_freq is None and cfs:
        adj_freq = cfs.adjustment_frequency.value if cfs.adjustment_frequency else None
    adj_freq_enum = AdjustmentFrequency(adj_freq) if adj_freq else None

    adj_custom_rate = data.adjustment_custom_rate
    if adj_custom_rate is None and cfs:
        adj_custom_rate = cfs.adjustment_custom_rate

    # Create client_lot with new contract fields
    cl = ClientLot(
        company_id=cid,
        client_id=data.client_id,
        lot_id=data.lot_id,
        purchase_date=data.purchase_date,
        total_value=data.total_value,
        down_payment=down_payment,
        total_installments=num_installments,
        current_cycle=1,
        current_installment_value=installment_value,
        annual_adjustment_rate=data.annual_adjustment_rate or Decimal("0.05"),
        penalty_rate=penalty_rate,
        daily_interest_rate=daily_interest_rate,
        adjustment_index=adj_index_enum,
        adjustment_frequency=adj_freq_enum,
        adjustment_custom_rate=adj_custom_rate,
        payment_plan=plan,
        status=ClientLotStatus.ACTIVE,
    )
    db.add(cl)
    await db.flush()

    # Mark lot as sold
    lot.status = LotStatus.SOLD
    await db.flush()

    # Generate first cycle invoices (max 12 per cycle)
    first_due_str = plan.get("first_due")
    first_due = date.fromisoformat(first_due_str) if first_due_str else data.purchase_date + timedelta(days=30)
    first_cycle_count = min(num_installments, 12)

    for i in range(first_cycle_count):
        due = first_due + timedelta(days=30 * i)
        invoice = Invoice(
            company_id=cid,
            client_lot_id=cl.id,
            due_date=due,
            amount=installment_value,
            installment_number=i + 1,
            status=InvoiceStatus.PENDING,
        )
        db.add(invoice)

    await db.flush()

    await log_audit(
        db, user_id=admin.id, company_id=cid,
        table_name="client_lots", operation="CREATE",
        resource_id=str(cl.id),
        detail=f"Lot {lot.lot_number} assigned to client {client.full_name}. "
               f"{first_cycle_count} invoices generated (cycle 1/{math.ceil(num_installments/12)})",
        ip_address=request.client.host if request.client else None,
    )

    return ClientLotResponse.model_validate(cl)


@router.get("/client-lots/{client_lot_id}", response_model=ClientLotResponse)
async def get_client_lot(
    client_lot_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_lots")),
):
    """Get a single client-lot with all financial fields."""
    result = await db.execute(
        select(ClientLot).where(
            ClientLot.id == client_lot_id,
            ClientLot.company_id == admin.company_id,
        )
    )
    cl = result.scalar_one_or_none()
    if not cl:
        raise HTTPException(status_code=404, detail="Client lot not found")
    return ClientLotResponse.model_validate(cl)


@router.patch("/client-lots/{client_lot_id}/financial-rules", response_model=ClientLotResponse)
async def update_client_lot_financial_rules(
    client_lot_id: UUID,
    data: ClientLotFinancialUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_lots")),
):
    """Update financial rules for a specific client-lot.

    These per-lot values override the company's global defaults.
    Send null for a field to clear the override (falls back to company default).
    """
    result = await db.execute(
        select(ClientLot).where(
            ClientLot.id == client_lot_id,
            ClientLot.company_id == admin.company_id,
        )
    )
    cl = result.scalar_one_or_none()
    if not cl:
        raise HTTPException(status_code=404, detail="Client lot not found")

    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        if field == "adjustment_index" and value is not None:
            value = AdjustmentIndex(value)
        elif field == "adjustment_frequency" and value is not None:
            value = AdjustmentFrequency(value)
        setattr(cl, field, value)

    await db.flush()

    await log_audit(
        db,
        user_id=admin.id,
        company_id=admin.company_id,
        table_name="client_lots",
        operation="UPDATE",
        resource_id=str(cl.id),
        detail=f"Financial rules updated: {list(updates.keys())}",
        ip_address=request.client.host if request.client else None,
    )

    return ClientLotResponse.model_validate(cl)


@router.post("/client-lots/{client_lot_id}/generate-next-batch")
async def generate_next_batch(
    client_lot_id: UUID,
    adjustment_rate: float = Query(..., ge=0, le=1, description="Adjustment rate (e.g., 0.05 for 5%)"),
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_financial")),
):
    """Generate next batch of 12 installments with adjustment.

    This endpoint is called when a cycle is complete and the admin wants
    to generate the next 12 boletos with an annual adjustment applied.

    The client lot's current_cycle will be incremented and the
    current_installment_value will be updated with the adjustment.
    """
    # Verify client lot exists
    result = await db.execute(
        select(ClientLot).where(
            ClientLot.id == client_lot_id,
            ClientLot.company_id == admin.company_id,
        )
    )
    cl = result.scalar_one_or_none()
    if not cl:
        raise HTTPException(status_code=404, detail="Client lot not found")

    # Check if ready for next batch
    should_gen, reason = await should_generate_next_batch(db, client_lot_id)
    if not should_gen:
        raise HTTPException(
            status_code=400,
            detail=f"Not ready for next batch: {reason}",
        )

    # Get installment info
    info = await get_remaining_installments(db, client_lot_id)
    if not info:
        raise HTTPException(status_code=404, detail="Could not calculate installment info")

    # Calculate new value with adjustment
    current_value = cl.current_installment_value
    if not current_value:
        total_installments = cl.total_installments or 1
        current_value = cl.total_value / total_installments

    new_value = current_value * Decimal(str(1 + adjustment_rate))
    new_value = new_value.quantize(Decimal("0.01"))

    # Update client lot
    cl.current_cycle += 1
    cl.current_installment_value = new_value
    cl.last_adjustment_date = date.today()

    await db.commit()

    logger.info(
        "generate_next_batch",
        client_lot_id=str(client_lot_id),
        admin_id=str(admin.id),
        new_cycle=cl.current_cycle,
        previous_value=float(current_value),
        new_value=float(new_value),
        adjustment_rate=adjustment_rate,
    )

    return {
        "status": "ready_for_batch",
        "client_lot_id": str(client_lot_id),
        "current_cycle": cl.current_cycle,
        "previous_installment_value": float(current_value),
        "new_installment_value": float(new_value),
        "adjustment_rate": adjustment_rate,
        "remaining_installments": info.remaining_installments,
        "message": (
            f"Ciclo {cl.current_cycle} preparado. Valor atualizado para R$ {new_value}. "
            f"Use o endpoint de criação de lotes para gerar os 12 boletos."
        ),
    }


@router.get("/client-lots/{client_lot_id}/installments")
async def get_client_lot_installments(
    client_lot_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_lots")),
):
    """Get installment information for a client lot.

    Returns:
        - total_installments: Total number of installments in the contract
        - paid_installments: Number of installments already paid
        - remaining_installments: Number of installments remaining
        - current_cycle: Current 12-installment cycle
        - next_cycle_number: Next cycle number
        - installments_in_current_cycle: Paid installments in current cycle
        - is_legacy_client: Whether this client uses manual paid_installments count
    """
    result = await db.execute(
        select(ClientLot).where(
            ClientLot.id == client_lot_id,
            ClientLot.company_id == admin.company_id,
        )
    )
    cl = result.scalar_one_or_none()
    if not cl:
        raise HTTPException(status_code=404, detail="Client lot not found")

    info = await get_remaining_installments(db, client_lot_id)
    if not info:
        raise HTTPException(status_code=500, detail="Could not calculate installment info")

    return {
        "client_lot_id": str(client_lot_id),
        "total_installments": info.total_installments,
        "paid_installments": info.paid_installments,
        "remaining_installments": info.remaining_installments,
        "current_cycle": info.current_cycle,
        "next_cycle_number": info.next_cycle_number,
        "installments_in_current_cycle": info.installments_in_current_cycle,
        "is_legacy_client": info.is_legacy_client,
        "current_installment_value": float(cl.current_installment_value) if cl.current_installment_value else None,
    }
