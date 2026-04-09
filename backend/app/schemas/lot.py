
"""Lot and Development schemas (Pydantic v2)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional, Dict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PropertyType


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
    status: Optional[str] = Field(None, pattern=r"^(available|reserved|sold)$")
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
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Lot Assignment (client_lots)
# ---------------------------------------------------------------------------

class LotAssignRequest(BaseModel):
    """Assign a lot to a client and optionally generate invoices."""

    client_id: UUID
    lot_id: UUID
    purchase_date: date
    total_value: Decimal = Field(..., gt=0)
    down_payment: Optional[Decimal] = Field(None, ge=0)
    total_installments: int = Field(1, ge=1, le=360)
    annual_adjustment_rate: Optional[Decimal] = Field(None, ge=0, le=1, description="Fixed annual rate on top of IPCA, default 0.05 (5%)")
    penalty_rate: Optional[Decimal] = Field(None, ge=0, le=1, description="Custom penalty rate for this client-lot, e.g. 0.02 = 2%")
    daily_interest_rate: Optional[Decimal] = Field(None, ge=0, le=0.01, description="Custom daily interest rate, e.g. 0.00033")
    adjustment_index: Optional[str] = Field(None, pattern=r"^(IPCA|IGPM|CUB|INPC)$", description="Price index: IPCA, IGPM, CUB, INPC")
    adjustment_frequency: Optional[str] = Field(None, pattern=r"^(MONTHLY|QUARTERLY|SEMIANNUAL|ANNUAL)$", description="Adjustment frequency")
    adjustment_custom_rate: Optional[Decimal] = Field(None, ge=0, le=1, description="Custom fixed rate on top of index, e.g. 0.05 = 5%")
    payment_plan: Optional[Dict[str, Any]] = Field(
        None,
        description="Installment details, e.g. {'installments': 120, 'first_due': '2024-03-01'}",
    )


class ClientLotResponse(BaseModel):
    """ClientLot read response."""

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
    previous_client_id: Optional[UUID] = None
    transfer_date: Optional[date] = None
    payment_plan: Optional[Dict[str, Any]] = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
