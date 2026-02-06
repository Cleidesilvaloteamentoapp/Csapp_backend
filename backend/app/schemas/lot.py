
"""Lot and Development schemas (Pydantic v2)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional, Dict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------

class DevelopmentCreate(BaseModel):
    """Payload for creating a development."""

    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    location: Optional[str] = None
    documents: Optional[Dict[str, Any]] = None


class DevelopmentUpdate(BaseModel):
    """Payload for updating a development."""

    name: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = None
    location: Optional[str] = None
    documents: Optional[Dict[str, Any]] = None


class DevelopmentResponse(BaseModel):
    """Development read response."""

    id: UUID
    company_id: UUID
    name: str
    description: Optional[str] = None
    location: Optional[str] = None
    documents: Optional[Dict[str, Any]] = None
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
    payment_plan: Optional[Dict[str, Any]] = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
