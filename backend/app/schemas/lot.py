"""Lot and Development schemas (Pydantic v2)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------

class DevelopmentCreate(BaseModel):
    """Payload for creating a development."""

    name: str = Field(..., min_length=2, max_length=255)
    description: str | None = None
    location: str | None = None
    documents: dict[str, Any] | None = None


class DevelopmentUpdate(BaseModel):
    """Payload for updating a development."""

    name: str | None = Field(None, min_length=2, max_length=255)
    description: str | None = None
    location: str | None = None
    documents: dict[str, Any] | None = None


class DevelopmentResponse(BaseModel):
    """Development read response."""

    id: UUID
    company_id: UUID
    name: str
    description: str | None = None
    location: str | None = None
    documents: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Lot
# ---------------------------------------------------------------------------

class LotCreate(BaseModel):
    """Payload for creating a lot."""

    development_id: UUID
    lot_number: str = Field(..., min_length=1, max_length=50)
    block: str | None = Field(None, max_length=50)
    area_m2: Decimal = Field(..., gt=0)
    price: Decimal = Field(..., gt=0)
    documents: dict[str, Any] | None = None


class LotUpdate(BaseModel):
    """Payload for updating a lot."""

    lot_number: str | None = Field(None, min_length=1, max_length=50)
    block: str | None = Field(None, max_length=50)
    area_m2: Decimal | None = Field(None, gt=0)
    price: Decimal | None = Field(None, gt=0)
    status: str | None = Field(None, pattern=r"^(available|reserved|sold)$")
    documents: dict[str, Any] | None = None


class LotResponse(BaseModel):
    """Lot read response."""

    id: UUID
    company_id: UUID
    development_id: UUID
    lot_number: str
    block: str | None = None
    area_m2: Decimal
    price: Decimal
    status: str
    documents: dict[str, Any] | None = None
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
    payment_plan: dict[str, Any] | None = Field(
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
    payment_plan: dict[str, Any] | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
