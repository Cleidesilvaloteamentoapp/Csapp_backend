from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
from app.models.enums import LotStatus, ClientLotStatus


class DevelopmentCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = None
    location: str


class DevelopmentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    description: Optional[str] = None
    location: Optional[str] = None


class DevelopmentResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    location: str
    documents: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime


class LotCreate(BaseModel):
    development_id: str
    lot_number: str
    block: Optional[str] = None
    area_m2: Decimal = Field(..., gt=0)
    price: Decimal = Field(..., gt=0)
    status: LotStatus = LotStatus.AVAILABLE


class LotUpdate(BaseModel):
    lot_number: Optional[str] = None
    block: Optional[str] = None
    area_m2: Optional[Decimal] = Field(None, gt=0)
    price: Optional[Decimal] = Field(None, gt=0)
    status: Optional[LotStatus] = None


class LotResponse(BaseModel):
    id: str
    development_id: str
    development_name: Optional[str] = None
    lot_number: str
    block: Optional[str] = None
    area_m2: Decimal
    price: Decimal
    status: LotStatus
    documents: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime


class PaymentPlanSchema(BaseModel):
    total_installments: int = Field(..., gt=0, le=360)
    installment_value: Decimal = Field(..., gt=0)
    first_due_date: date
    down_payment: Optional[Decimal] = Field(None, ge=0)


class ClientLotCreate(BaseModel):
    client_id: str
    lot_id: str
    purchase_date: date
    total_value: Decimal = Field(..., gt=0)
    payment_plan: PaymentPlanSchema


class ClientLotResponse(BaseModel):
    id: str
    client_id: str
    client_name: Optional[str] = None
    lot_id: str
    lot_number: Optional[str] = None
    development_name: Optional[str] = None
    purchase_date: date
    total_value: Decimal
    payment_plan: dict
    status: ClientLotStatus
    created_at: datetime


class LotFilters(BaseModel):
    development_id: Optional[str] = None
    status: Optional[LotStatus] = None
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None
    page: int = 1
    page_size: int = 20
