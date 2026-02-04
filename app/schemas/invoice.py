from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
from app.models.enums import InvoiceStatus


class InvoiceCreate(BaseModel):
    client_lot_id: str
    due_date: date
    amount: Decimal = Field(..., gt=0)
    installment_number: int = Field(..., gt=0)


class InvoiceResponse(BaseModel):
    id: str
    client_lot_id: str
    asaas_payment_id: Optional[str] = None
    due_date: date
    amount: Decimal
    status: InvoiceStatus
    installment_number: int
    barcode: Optional[str] = None
    payment_url: Optional[str] = None
    paid_at: Optional[datetime] = None
    created_at: datetime
    
    lot_number: Optional[str] = None
    development_name: Optional[str] = None


class InvoiceListResponse(BaseModel):
    items: List[InvoiceResponse]
    total: int
    total_pending: Decimal
    total_paid: Decimal
    total_overdue: Decimal


class InvoiceFilters(BaseModel):
    client_lot_id: Optional[str] = None
    status: Optional[InvoiceStatus] = None
    due_date_from: Optional[date] = None
    due_date_to: Optional[date] = None
    page: int = 1
    page_size: int = 20


class AsaasWebhookPayload(BaseModel):
    event: str
    payment: dict
