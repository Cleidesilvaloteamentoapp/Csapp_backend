
"""Lot and Development schemas (Pydantic v2)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional, Dict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import PropertyType
from app.schemas.financial_settings import rate_from_percent, rate_to_percent


# ---------------------------------------------------------------------------
# Photos (shared by Development and Lot galleries)
# ---------------------------------------------------------------------------

class PhotoOut(BaseModel):
    """A single photo in a development/lot gallery (enriched with a signed URL)."""

    id: str
    path: Optional[str] = None
    url: Optional[str] = None
    is_primary: bool = False
    visible_to_client: bool = False
    caption: Optional[str] = None


class PhotoUpdate(BaseModel):
    """Toggle a photo's primary flag / client visibility / caption."""

    is_primary: Optional[bool] = None
    visible_to_client: Optional[bool] = None
    caption: Optional[str] = Field(None, max_length=255)


# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------

class DevelopmentCreate(BaseModel):
    """Payload for creating a development."""

    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    location: Optional[str] = None
    property_type: PropertyType = PropertyType.LOT
    documents: Optional[Dict[str, Any]] = None

    # Lot-specific fields
    block: Optional[str] = Field(None, max_length=50)
    lot_number: Optional[str] = Field(None, max_length=50)
    area_m2: Optional[Decimal] = Field(None, gt=0)

    # Residential-specific fields
    bedrooms: Optional[int] = Field(None, ge=0)
    bathrooms: Optional[int] = Field(None, ge=0)
    suites: Optional[int] = Field(None, ge=0)
    parking_spaces: Optional[int] = Field(None, ge=0)
    construction_area_m2: Optional[Decimal] = Field(None, gt=0)
    total_area_m2: Optional[Decimal] = Field(None, gt=0)

    # General fields
    price: Optional[Decimal] = Field(None, gt=0)


class DevelopmentUpdate(BaseModel):
    """Payload for updating a development."""

    name: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = None
    location: Optional[str] = None
    property_type: Optional[PropertyType] = None
    documents: Optional[Dict[str, Any]] = None

    # Lot-specific fields
    block: Optional[str] = Field(None, max_length=50)
    lot_number: Optional[str] = Field(None, max_length=50)
    area_m2: Optional[Decimal] = Field(None, gt=0)

    # Residential-specific fields
    bedrooms: Optional[int] = Field(None, ge=0)
    bathrooms: Optional[int] = Field(None, ge=0)
    suites: Optional[int] = Field(None, ge=0)
    parking_spaces: Optional[int] = Field(None, ge=0)
    construction_area_m2: Optional[Decimal] = Field(None, gt=0)
    total_area_m2: Optional[Decimal] = Field(None, gt=0)

    # General fields
    price: Optional[Decimal] = Field(None, gt=0)


class DevelopmentResponse(BaseModel):
    """Development read response."""

    id: UUID
    company_id: UUID
    name: str
    description: Optional[str] = None
    location: Optional[str] = None
    property_type: PropertyType
    documents: Optional[Dict[str, Any]] = None
    photos: list[PhotoOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    # Lot-specific fields
    block: Optional[str] = None
    lot_number: Optional[str] = None
    area_m2: Optional[Decimal] = None

    # Residential-specific fields
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    suites: Optional[int] = None
    parking_spaces: Optional[int] = None
    construction_area_m2: Optional[Decimal] = None
    total_area_m2: Optional[Decimal] = None

    # General fields
    price: Optional[Decimal] = None

    model_config = ConfigDict(from_attributes=True)


class DevelopmentFilter(BaseModel):
    """Filter parameters for listing developments."""

    property_type: Optional[PropertyType] = None
    name: Optional[str] = None
    location: Optional[str] = None
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None


# ---------------------------------------------------------------------------
# Lot
# ---------------------------------------------------------------------------

class LotCreate(BaseModel):
    """Payload for creating a lot."""

    development_id: UUID
    lot_number: str = Field(..., min_length=1, max_length=50)
    block: Optional[str] = Field(None, max_length=50)
    area_m2: Decimal = Field(..., gt=0)
    price: Decimal = Field(..., gt=0)
    documents: Optional[Dict[str, Any]] = None


class LotUpdate(BaseModel):
    """Payload for updating a lot."""

    lot_number: Optional[str] = Field(None, min_length=1, max_length=50)
    block: Optional[str] = Field(None, max_length=50)
    area_m2: Optional[Decimal] = Field(None, gt=0)
    price: Optional[Decimal] = Field(None, gt=0)
    status: Optional[str] = Field(None, pattern=r"(?i)^(available|reserved|sold)$")
    documents: Optional[Dict[str, Any]] = None


class LotResponse(BaseModel):
    """Lot read response."""

    id: UUID
    company_id: UUID
    development_id: UUID
    lot_number: str
    block: Optional[str] = None
    area_m2: Decimal
    price: Decimal
    status: str
    documents: Optional[Dict[str, Any]] = None
    photos: list[PhotoOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Lot Assignment (client_lots)
# ---------------------------------------------------------------------------

class LotAssignRequest(BaseModel):
    """Assign a lot to a client and optionally generate invoices.

    All rate fields accept percentages: send 2 for 2%, 0.5 for 0.5%.
    """

    client_id: UUID
    lot_id: UUID
    purchase_date: date
    total_value: Decimal = Field(..., gt=0)
    down_payment: Optional[Decimal] = Field(None, ge=0)
    total_installments: Optional[int] = Field(None, ge=1, le=360, description="Number of installments. If omitted, derived from monthly value in payment_plan.")
    annual_adjustment_rate: Optional[Decimal] = Field(None, description="Fixed annual rate on top of IPCA in %, e.g. 5 = 5%")
    penalty_rate: Optional[Decimal] = Field(None, description="Custom penalty rate in %, e.g. 2 = 2%")
    daily_interest_rate: Optional[Decimal] = Field(None, description="Custom daily interest rate in %, e.g. 0.033 = 0.033%/day")
    adjustment_index: Optional[str] = Field(None, pattern=r"^(IPCA|IGPM|CUB|INPC)$", description="Price index: IPCA, IGPM, CUB, INPC")
    adjustment_frequency: Optional[str] = Field(None, pattern=r"^(MONTHLY|QUARTERLY|SEMIANNUAL|ANNUAL)$", description="Adjustment frequency")
    adjustment_custom_rate: Optional[Decimal] = Field(None, description="Custom fixed rate on top of index in %, e.g. 5 = 5%")
    manual_index_value: Optional[Decimal] = Field(None, description="Manual index value in %, e.g. IPCA do dia = 0.5 for 0.5%. Overrides the economic_indices lookup for this contract.")
    payment_plan: Optional[Dict[str, Any]] = Field(
        None,
        description="Installment details, e.g. {'installments': 120, 'first_due': '2024-03-01'}",
    )

    @field_validator("penalty_rate", "adjustment_custom_rate", "annual_adjustment_rate", mode="before")
    @classmethod
    def percent_to_decimal(cls, v):
        return rate_from_percent(v, max_percent=100)

    @field_validator("daily_interest_rate", mode="before")
    @classmethod
    def daily_percent_to_decimal(cls, v):
        return rate_from_percent(v, max_percent=1)


class ClientLotResponse(BaseModel):
    """ClientLot read response.

    All rate fields are returned as percentages (e.g. 2 = 2%).
    """

    id: UUID
    company_id: UUID
    client_id: UUID
    lot_id: UUID
    purchase_date: date
    total_value: Decimal
    down_payment: Optional[Decimal] = None
    total_installments: int = 1
    current_cycle: int = 1
    current_installment_value: Optional[Decimal] = None
    annual_adjustment_rate: Optional[Decimal] = None
    last_adjustment_date: Optional[date] = None
    last_cycle_paid_at: Optional[date] = None
    penalty_rate: Optional[Decimal] = None
    daily_interest_rate: Optional[Decimal] = None
    adjustment_index: Optional[str] = None
    adjustment_frequency: Optional[str] = None
    adjustment_custom_rate: Optional[Decimal] = None
    manual_index_value: Optional[Decimal] = None
    previous_client_id: Optional[UUID] = None
    transfer_date: Optional[date] = None
    payment_plan: Optional[Dict[str, Any]] = None
    status: str
    created_at: datetime
    updated_at: datetime

    # Optional property context, populated by the client portal (my-lots).
    # Defaults keep admin endpoints (which validate a bare ClientLot) unaffected.
    lot_number: Optional[str] = None
    block: Optional[str] = None
    development_name: Optional[str] = None
    lot_photos: list[PhotoOut] = Field(default_factory=list)
    development_photos: list[PhotoOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

    @field_validator(
        "penalty_rate", "daily_interest_rate",
        "adjustment_custom_rate", "annual_adjustment_rate",
        mode="before",
    )
    @classmethod
    def db_to_percent(cls, v):
        return rate_to_percent(v)


# ---------------------------------------------------------------------------
# Payment plan preview (dry-run calculation + effective rates)
# ---------------------------------------------------------------------------

class PaymentPlanPreviewRequest(BaseModel):
    """Dry-run: compute the payment plan and resolve effective rates without persisting.

    Provide either ``total_installments`` or ``monthly_value`` (the other is derived).
    Rate fields accept percentages (2 = 2%) and are optional per-lot overrides used
    to preview the effective rates the contract would receive.
    """

    total_value: Decimal = Field(..., gt=0)
    down_payment: Optional[Decimal] = Field(None, ge=0)
    total_installments: Optional[int] = Field(None, ge=1, le=360)
    monthly_value: Optional[Decimal] = Field(None, gt=0)
    purchase_date: Optional[date] = None
    first_due: Optional[date] = None
    penalty_rate: Optional[Decimal] = None
    daily_interest_rate: Optional[Decimal] = None
    adjustment_index: Optional[str] = Field(None, pattern=r"^(IPCA|IGPM|CUB|INPC)$")
    adjustment_frequency: Optional[str] = Field(None, pattern=r"^(MONTHLY|QUARTERLY|SEMIANNUAL|ANNUAL)$")
    adjustment_custom_rate: Optional[Decimal] = None

    @field_validator("penalty_rate", "adjustment_custom_rate", mode="before")
    @classmethod
    def percent_to_decimal(cls, v):
        return rate_from_percent(v, max_percent=100)

    @field_validator("daily_interest_rate", mode="before")
    @classmethod
    def daily_percent_to_decimal(cls, v):
        return rate_from_percent(v, max_percent=1)


class EffectiveRatesResponse(BaseModel):
    """Effective rates resolved per-lot → company → hardcoded, as percentages."""

    penalty_rate: Decimal
    daily_interest_rate: Decimal
    adjustment_index: str
    adjustment_frequency: str
    adjustment_custom_rate: Decimal


class PaymentPlanPreviewResponse(BaseModel):
    """Computed payment plan plus the effective rates that would apply."""

    total_value: Decimal
    down_payment: Decimal
    financed_value: Decimal
    installments: int
    monthly_value: Decimal
    last_installment_value: Decimal
    has_residue: bool
    first_due: Optional[date] = None
    effective_rates: EffectiveRatesResponse
