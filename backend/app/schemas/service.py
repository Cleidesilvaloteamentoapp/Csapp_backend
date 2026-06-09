from typing import Optional

"""Service type and service order schemas (Pydantic v2)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Service Types
# ---------------------------------------------------------------------------

class ServiceTypeCreate(BaseModel):
    """Payload for creating a service type."""

    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    base_price: Decimal = Field(0, ge=0)
    is_active: bool = True


class ServiceTypeUpdate(BaseModel):
    """Payload for updating a service type."""

    name: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = None
    base_price: Optional[Decimal] = Field(None, ge=0)
    is_active: Optional[bool] = None


class ServiceTypeResponse(BaseModel):
    """Service type read response."""

    id: UUID
    company_id: UUID
    name: str
    description: Optional[str] = None
    base_price: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Service Orders
# ---------------------------------------------------------------------------

class ServiceOrderCreate(BaseModel):
    """Payload for a client to request a service."""

    service_type_id: UUID
    lot_id: Optional[UUID] = None
    notes: Optional[str] = None


class ServiceOrderStatusUpdate(BaseModel):
    """Update order status (admin)."""

    status: str = Field(..., pattern=r"^(requested|approved|in_progress|completed|cancelled)$")


class ServiceOrderFinancialUpdate(BaseModel):
    """Update cost / revenue of an order (admin)."""

    cost: Optional[Decimal] = Field(None, ge=0)
    revenue: Optional[Decimal] = Field(None, ge=0)


class ServiceOrderResponse(BaseModel):
    """Service order read response."""

    id: UUID
    company_id: UUID
    client_id: UUID
    lot_id: Optional[UUID] = None
    service_type_id: UUID
    requested_date: date
    execution_date: Optional[date] = None
    status: str
    cost: Decimal
    revenue: Decimal
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    # Requester / service info (populated via from_order)
    client_name: Optional[str] = None
    client_cpf_cnpj: Optional[str] = None
    service_type_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_order(cls, order) -> "ServiceOrderResponse":
        """Build the response including the requesting client and service type names."""
        resp = cls.model_validate(order)
        client = getattr(order, "client", None)
        if client is not None:
            resp.client_name = getattr(client, "full_name", None)
            resp.client_cpf_cnpj = getattr(client, "cpf_cnpj", None)
        service_type = getattr(order, "service_type", None)
        if service_type is not None:
            resp.service_type_name = getattr(service_type, "name", None)
        return resp
