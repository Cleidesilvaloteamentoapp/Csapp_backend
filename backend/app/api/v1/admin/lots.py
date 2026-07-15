from typing import Optional

"""Admin lot and development management endpoints."""

import math
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

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
from app.services.financial_defaults_service import get_all_effective_rates
from app.services.pricing_service import compute_plan
from app.services.storage_service import delete_file, enrich_photos, upload_file
from app.utils.exceptions import StorageError
from app.utils.logging import get_logger
from app.schemas.financial_settings import ClientLotFinancialUpdate, rate_to_percent
from app.schemas.lot import (
    ClientLotResponse,
    DevelopmentCreate,
    DevelopmentFilter,
    DevelopmentResponse,
    DevelopmentUpdate,
    EffectiveRatesResponse,
    LotAssignRequest,
    LotCreate,
    LotResponse,
    LotUpdate,
    PaymentPlanPreviewRequest,
    PaymentPlanPreviewResponse,
    PhotoUpdate,
)

router = APIRouter(prefix="/lots", tags=["Admin Lots"])

logger = get_logger(__name__)
dev_router = APIRouter(prefix="/developments", tags=["Admin Developments"])

ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/jpg", "image/webp", "image/gif"}
MAX_PHOTO_SIZE = 10 * 1024 * 1024  # 10 MB


def _dev_response(dev: Development) -> dict:
    """Serialize a development, enriching photos with fresh signed URLs."""
    data = DevelopmentResponse.model_validate(dev).model_dump()
    data["photos"] = enrich_photos(dev.photos or [])
    return data


def _lot_response(lot: Lot) -> dict:
    """Serialize a lot, enriching photos with fresh signed URLs."""
    data = LotResponse.model_validate(lot).model_dump()
    data["photos"] = enrich_photos(lot.photos or [])
    return data


async def _add_photo(entity, *, company_id, subfolder: str, file: UploadFile,
                     is_primary: bool, visible_to_client: bool, caption: Optional[str]) -> dict:
    """Upload a photo file and append it to the entity's JSONB photos list."""
    if file.content_type not in ALLOWED_PHOTO_TYPES:
        raise HTTPException(status_code=400, detail="Tipo de imagem não permitido (use JPG, PNG, WEBP ou GIF)")
    contents = await file.read()
    if len(contents) > MAX_PHOTO_SIZE:
        raise HTTPException(status_code=400, detail=f"Imagem excede o tamanho máximo de {MAX_PHOTO_SIZE // (1024*1024)} MB")
    try:
        path = await upload_file(
            file_bytes=contents,
            original_filename=file.filename or "photo.jpg",
            company_id=str(company_id),
            subfolder=subfolder,
        )
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from exc

    photos = list(entity.photos or [])
    # First photo of an entity becomes primary automatically.
    if is_primary or not photos:
        for p in photos:
            p["is_primary"] = False
        is_primary = True
    photo = {
        "id": uuid4().hex,
        "path": path,
        "is_primary": is_primary,
        "visible_to_client": visible_to_client,
        "caption": caption,
    }
    photos.append(photo)
    entity.photos = photos
    flag_modified(entity, "photos")
    return photo


def _update_photo(entity, photo_id: str, data: PhotoUpdate) -> None:
    """Mutate a single photo's flags/caption in the entity's photos list."""
    photos = list(entity.photos or [])
    target = next((p for p in photos if p.get("id") == photo_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Photo not found")
    if data.is_primary is True:
        for p in photos:
            p["is_primary"] = False
        target["is_primary"] = True
    elif data.is_primary is False:
        target["is_primary"] = False
    if data.visible_to_client is not None:
        target["visible_to_client"] = data.visible_to_client
    if data.caption is not None:
        target["caption"] = data.caption
    entity.photos = photos
    flag_modified(entity, "photos")


async def _delete_photo(entity, photo_id: str) -> None:
    """Remove a photo from the entity and delete its file from storage."""
    photos = list(entity.photos or [])
    target = next((p for p in photos if p.get("id") == photo_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Photo not found")
    remaining = [p for p in photos if p.get("id") != photo_id]
    # If we removed the primary photo, promote the first remaining one.
    if target.get("is_primary") and remaining:
        remaining[0]["is_primary"] = True
    entity.photos = remaining
    flag_modified(entity, "photos")
    if target.get("path"):
        try:
            await delete_file(target["path"])
        except StorageError:
            pass  # File may already be gone


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
    return [_dev_response(d) for d in rows.scalars().all()]


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
    return _dev_response(dev)


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
    return _dev_response(dev)


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
    return _dev_response(dev)


async def _get_owned_development(db: AsyncSession, dev_id: UUID, company_id: UUID) -> Development:
    dev = (await db.execute(
        select(Development).where(Development.id == dev_id, Development.company_id == company_id)
    )).scalar_one_or_none()
    if not dev:
        raise HTTPException(status_code=404, detail="Development not found")
    return dev


@dev_router.post("/{dev_id}/photos", response_model=DevelopmentResponse, status_code=status.HTTP_201_CREATED)
async def add_development_photo(
    dev_id: UUID,
    file: UploadFile = File(...),
    is_primary: bool = Form(False),
    visible_to_client: bool = Form(False),
    caption: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_lots")),
):
    """Upload a photo to a development gallery."""
    dev = await _get_owned_development(db, dev_id, admin.company_id)
    await _add_photo(
        dev, company_id=admin.company_id, subfolder=f"developments/{dev_id}/photos",
        file=file, is_primary=is_primary, visible_to_client=visible_to_client, caption=caption,
    )
    await db.flush()
    return _dev_response(dev)


@dev_router.patch("/{dev_id}/photos/{photo_id}", response_model=DevelopmentResponse)
async def update_development_photo(
    dev_id: UUID,
    photo_id: str,
    data: PhotoUpdate,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_lots")),
):
    """Toggle a development photo's primary flag / client visibility / caption."""
    dev = await _get_owned_development(db, dev_id, admin.company_id)
    _update_photo(dev, photo_id, data)
    await db.flush()
    return _dev_response(dev)


@dev_router.delete("/{dev_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_development(
    dev_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_lots")),
):
    """Delete a development and all its lots.

    Blocked if any lot in this development is SOLD (has an active contract).
    """
    dev = await _get_owned_development(db, dev_id, admin.company_id)

    # Check for SOLD lots — those have active contracts and cannot be removed
    sold = (await db.execute(
        select(Lot).where(
            Lot.development_id == dev_id,
            Lot.status == LotStatus.SOLD,
            Lot.company_id == admin.company_id,
        )
    )).scalars().first()
    if sold:
        raise HTTPException(
            status_code=400,
            detail="Não é possível excluir: o empreendimento possui lote(s) vendido(s) com contrato ativo.",
        )

    await log_audit(
        db, user_id=admin.id, company_id=admin.company_id,
        table_name="developments", operation="DELETE",
        resource_id=str(dev_id),
        detail=f"Empreendimento '{dev.name}' excluído.",
        ip_address=request.client.host if request.client else None,
    )

    await db.delete(dev)
    await db.flush()
    return None


@dev_router.delete("/{dev_id}/photos/{photo_id}", response_model=DevelopmentResponse)
async def delete_development_photo(
    dev_id: UUID,
    photo_id: str,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_lots")),
):
    """Remove a photo from a development gallery."""
    dev = await _get_owned_development(db, dev_id, admin.company_id)
    await _delete_photo(dev, photo_id)
    await db.flush()
    return _dev_response(dev)


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
    items = [_lot_response(r) for r in rows.scalars().all()]

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

    # Evita terrenos duplicados: a matrícula é única por empresa.
    dup = (await db.execute(
        select(Lot).where(
            Lot.company_id == admin.company_id,
            func.lower(Lot.registration_number) == data.registration_number.lower(),
        )
    )).scalar_one_or_none()
    if dup:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Já existe um lote cadastrado com a matrícula {data.registration_number}"
                f"{f' (balneário {dup.balneario})' if dup.balneario else ''}."
            ),
        )

    lot = Lot(company_id=admin.company_id, **data.model_dump())
    db.add(lot)
    try:
        await db.flush()
    except IntegrityError:
        # Rede de segurança contra corrida entre a checagem acima e o insert.
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Já existe um lote cadastrado com a matrícula {data.registration_number}.",
        )
    return _lot_response(lot)


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
    return _lot_response(lot)


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
            # Enum values are uppercase; accept any case from the UI.
            v = LotStatus(str(v).upper())
        setattr(lot, k, v)
    await db.flush()
    return _lot_response(lot)


async def _get_owned_lot(db: AsyncSession, lot_id: UUID, company_id: UUID) -> Lot:
    lot = (await db.execute(
        select(Lot).where(Lot.id == lot_id, Lot.company_id == company_id)
    )).scalar_one_or_none()
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")
    return lot


@router.post("/{lot_id}/photos", response_model=LotResponse, status_code=status.HTTP_201_CREATED)
async def add_lot_photo(
    lot_id: UUID,
    file: UploadFile = File(...),
    is_primary: bool = Form(False),
    visible_to_client: bool = Form(False),
    caption: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_lots")),
):
    """Upload a photo to a lot gallery."""
    lot = await _get_owned_lot(db, lot_id, admin.company_id)
    await _add_photo(
        lot, company_id=admin.company_id, subfolder=f"lots/{lot_id}/photos",
        file=file, is_primary=is_primary, visible_to_client=visible_to_client, caption=caption,
    )
    await db.flush()
    return _lot_response(lot)


@router.patch("/{lot_id}/photos/{photo_id}", response_model=LotResponse)
async def update_lot_photo(
    lot_id: UUID,
    photo_id: str,
    data: PhotoUpdate,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_lots")),
):
    """Toggle a lot photo's primary flag / client visibility / caption."""
    lot = await _get_owned_lot(db, lot_id, admin.company_id)
    _update_photo(lot, photo_id, data)
    await db.flush()
    return _lot_response(lot)


@router.delete("/{lot_id}/photos/{photo_id}", response_model=LotResponse)
async def delete_lot_photo(
    lot_id: UUID,
    photo_id: str,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_lots")),
):
    """Remove a photo from a lot gallery."""
    lot = await _get_owned_lot(db, lot_id, admin.company_id)
    await _delete_photo(lot, photo_id)
    await db.flush()
    return _lot_response(lot)


@router.delete("/{lot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lot(
    lot_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_lots")),
):
    """Delete a lot.

    Blocked only if an ACTIVE contract (client_lot) still references it. A lot
    left as SOLD but orphaned (e.g. client deleted without unlinking) can be
    deleted — the SOLD status alone must not lock it forever.
    """
    lot = await _get_owned_lot(db, lot_id, admin.company_id)

    active_contract = (await db.execute(
        select(ClientLot).where(
            ClientLot.lot_id == lot_id,
            ClientLot.status == ClientLotStatus.ACTIVE,
        )
    )).scalar_one_or_none()
    if active_contract:
        raise HTTPException(
            status_code=400,
            detail="Não é possível excluir um lote vendido com contrato ativo.",
        )

    await log_audit(
        db, user_id=admin.id, company_id=admin.company_id,
        table_name="lots", operation="DELETE",
        resource_id=str(lot_id),
        detail=f"Lote {lot.lot_number} (quadra {lot.block}) excluído.",
        ip_address=request.client.host if request.client else None,
    )

    await db.delete(lot)
    await db.flush()
    return None


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

    # Calculate the payment plan (bidirectional: parcelas <-> valor mensal).
    # Authoritative source of truth lives in pricing_service.compute_plan.
    plan = data.payment_plan or {}
    down_payment = data.down_payment or Decimal("0")
    explicit_installments = data.total_installments or plan.get("installments")
    plan_monthly = plan.get("monthly_value")
    try:
        computed = compute_plan(
            total_value=data.total_value,
            down_payment=down_payment,
            installments=int(explicit_installments) if explicit_installments else None,
            monthly_value=plan_monthly,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    num_installments = computed.installments
    installment_value = computed.monthly_value
    # Persist the computed plan back into payment_plan for transparency/audit.
    plan = {
        **plan,
        "installments": num_installments,
        "monthly_value": str(installment_value),
        "financed_value": str(computed.financed_value),
        "last_installment_value": str(computed.last_installment_value),
    }

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

    # Legacy client (cliente antigo): contract already in progress. We record the
    # link and how many installments were already paid, but we DON'T generate any
    # invoices/boletos now — the next annual emission picks up from the right cycle.
    paid_installments = 0
    starting_cycle = 1
    if data.is_legacy:
        paid_installments = min(data.paid_installments or 0, num_installments)
        # Each cycle is 12 installments; a completed cycle rolls into the next one.
        starting_cycle = (paid_installments // 12) + 1

    # Create client_lot with new contract fields
    cl = ClientLot(
        company_id=cid,
        client_id=data.client_id,
        lot_id=data.lot_id,
        purchase_date=data.purchase_date,
        total_value=data.total_value,
        down_payment=down_payment,
        total_installments=num_installments,
        paid_installments=paid_installments,
        current_cycle=starting_cycle,
        current_installment_value=installment_value,
        annual_adjustment_rate=data.annual_adjustment_rate or Decimal("0.05"),
        penalty_rate=penalty_rate,
        daily_interest_rate=daily_interest_rate,
        adjustment_index=adj_index_enum,
        adjustment_frequency=adj_freq_enum,
        adjustment_custom_rate=adj_custom_rate,
        manual_index_value=data.manual_index_value,
        payment_plan=plan,
        status=ClientLotStatus.ACTIVE,
    )
    db.add(cl)
    await db.flush()

    # Mark lot as sold
    lot.status = LotStatus.SOLD
    await db.flush()

    # For a legacy client we intentionally skip invoice generation: the contract
    # is already running and its boletos will be issued on the next annual cycle.
    if data.is_legacy:
        await db.flush()
        await log_audit(
            db, user_id=admin.id, company_id=cid,
            table_name="client_lots", operation="CREATE",
            resource_id=str(cl.id),
            detail=f"Lot {lot.lot_number} assigned to legacy client {client.full_name} "
                   f"(cliente antigo). No invoices generated; {paid_installments} "
                   f"installment(s) marked as paid, resuming at cycle {starting_cycle}.",
            ip_address=request.client.host if request.client else None,
        )
        return ClientLotResponse.model_validate(cl)

    # Generate first cycle invoices (max 12 per cycle)
    first_due_str = plan.get("first_due")
    first_due = date.fromisoformat(first_due_str) if first_due_str else data.purchase_date + timedelta(days=30)
    first_cycle_count = min(num_installments, 12)

    for i in range(first_cycle_count):
        # Use relativedelta so the day-of-month is preserved across months
        # (timedelta(days=30*i) drifts day 20 -> day 19 on 31-day months).
        due = first_due + relativedelta(months=i)
        installment_number = i + 1
        # The final installment of the whole contract absorbs the rounding residue.
        amount = (
            computed.last_installment_value
            if installment_number == num_installments
            else installment_value
        )
        invoice = Invoice(
            company_id=cid,
            client_lot_id=cl.id,
            due_date=due,
            amount=amount,
            installment_number=installment_number,
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


@router.post("/assign/preview", response_model=PaymentPlanPreviewResponse)
async def preview_assign(
    data: PaymentPlanPreviewRequest,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_lots")),
):
    """Dry-run the payment plan + effective rates without persisting anything.

    Lets the frontend show the critical fields (valor financiado, parcelas, valor
    mensal e taxas efetivas) for confirmation before the sale is committed.
    """
    try:
        computed = compute_plan(
            total_value=data.total_value,
            down_payment=data.down_payment,
            installments=data.total_installments,
            monthly_value=data.monthly_value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Resolve effective rates via a transient (unpersisted) ClientLot so we reuse
    # the same per-lot → company → hardcoded fallback logic used at billing time.
    transient = ClientLot(
        company_id=admin.company_id,
        penalty_rate=data.penalty_rate,
        daily_interest_rate=data.daily_interest_rate,
        adjustment_index=AdjustmentIndex(data.adjustment_index) if data.adjustment_index else None,
        adjustment_frequency=AdjustmentFrequency(data.adjustment_frequency) if data.adjustment_frequency else None,
        adjustment_custom_rate=data.adjustment_custom_rate,
    )
    rates = await get_all_effective_rates(db, transient)

    effective = EffectiveRatesResponse(
        penalty_rate=rate_to_percent(rates["penalty_rate"]),
        daily_interest_rate=rate_to_percent(rates["daily_interest_rate"]),
        adjustment_index=rates["adjustment_index"].value,
        adjustment_frequency=rates["adjustment_frequency"].value,
        adjustment_custom_rate=rate_to_percent(rates["adjustment_custom_rate"]),
    )

    first_due = data.first_due
    if first_due is None and data.purchase_date is not None:
        first_due = data.purchase_date + timedelta(days=30)

    return PaymentPlanPreviewResponse(
        total_value=computed.total_value,
        down_payment=computed.down_payment,
        financed_value=computed.financed_value,
        installments=computed.installments,
        monthly_value=computed.monthly_value,
        last_installment_value=computed.last_installment_value,
        has_residue=computed.has_residue,
        first_due=first_due,
        effective_rates=effective,
    )


@router.delete("/assign/{client_lot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_lot(
    client_lot_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_lots")),
):
    """Unassign a lot from a client (desvincular).

    Only allowed while no installment has been paid: deletes the client_lot and
    its (pending) invoices and frees the lot back to AVAILABLE. If any invoice is
    already PAID, the assignment is kept to preserve financial history.
    """
    cid = admin.company_id

    cl = (await db.execute(
        select(ClientLot).where(ClientLot.id == client_lot_id, ClientLot.company_id == cid)
    )).scalar_one_or_none()
    if not cl:
        raise HTTPException(status_code=404, detail="Vínculo (client_lot) não encontrado")

    invoices = (await db.execute(
        select(Invoice).where(Invoice.client_lot_id == cl.id)
    )).scalars().all()

    if any(inv.status == InvoiceStatus.PAID for inv in invoices):
        raise HTTPException(
            status_code=400,
            detail="Não é possível desvincular: já existem parcelas pagas neste contrato.",
        )

    for inv in invoices:
        await db.delete(inv)

    # Free the lot back to AVAILABLE
    lot = (await db.execute(
        select(Lot).where(Lot.id == cl.lot_id, Lot.company_id == cid)
    )).scalar_one_or_none()
    if lot:
        lot.status = LotStatus.AVAILABLE

    await db.delete(cl)
    await db.flush()

    await log_audit(
        db, user_id=admin.id, company_id=cid,
        table_name="client_lots", operation="DELETE",
        resource_id=str(client_lot_id),
        detail=f"Lote desvinculado do cliente {cl.client_id}. {len(invoices)} faturas removidas.",
        ip_address=request.client.host if request.client else None,
    )
    return None


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

    # Calculate new value with adjustment.
    # The fallback must subtract down_payment so the parcel reflects the
    # financed amount, not the total contract value.
    current_value = cl.current_installment_value
    if not current_value:
        total_installments = cl.total_installments or 1
        financed = cl.total_value - (cl.down_payment or Decimal("0"))
        current_value = financed / total_installments

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
