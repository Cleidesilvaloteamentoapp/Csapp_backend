from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
from app.models.enums import ServiceOrderStatus


class ServiceTypeCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = None
    base_price: Decimal = Field(..., ge=0)
    is_active: bool = True


class ServiceTypeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = None
    base_price: Optional[Decimal] = Field(None, ge=0)
    is_active: Optional[bool] = None


class ServiceTypeResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    base_price: Decimal
    is_active: bool
    created_at: datetime


class ServiceOrderCreate(BaseModel):
    lot_id: Optional[str] = None
    service_type_id: str
    requested_date: date
    notes: Optional[str] = None


class ServiceOrderUpdate(BaseModel):
    execution_date: Optional[date] = None
    status: Optional[ServiceOrderStatus] = None
    cost: Optional[Decimal] = Field(None, ge=0)
    revenue: Optional[Decimal] = Field(None, ge=0)
    notes: Optional[str] = None


class ServiceOrderResponse(BaseModel):
    id: str
    client_id: str
    client_name: Optional[str] = None
    lot_id: Optional[str] = None
    lot_number: Optional[str] = None
    service_type_id: str
    service_type_name: Optional[str] = None
    requested_date: date
    execution_date: Optional[date] = None
    status: ServiceOrderStatus
    cost: Decimal
    revenue: Optional[Decimal] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ServiceOrderFilters(BaseModel):
    client_id: Optional[str] = None
    status: Optional[ServiceOrderStatus] = None
    service_type_id: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    page: int = 1
    page_size: int = 20


class ServiceAnalytics(BaseModel):
    total_orders: int
    total_cost: Decimal
    total_revenue: Decimal
    profit: Decimal
    orders_by_status: dict
    orders_by_type: dict
