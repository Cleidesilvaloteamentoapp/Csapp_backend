"""Invoice schemas (Pydantic v2)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class InvoiceResponse(BaseModel):
    """Invoice / boleto read response."""

    id: UUID
    company_id: UUID
    client_lot_id: UUID
    due_date: date
    amount: Decimal
    installment_number: int
    status: str
    asaas_payment_id: str | None = None
    barcode: str | None = None
    payment_url: str | None = None
    paid_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
