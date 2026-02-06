from typing import Optional

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
    asaas_payment_id: Optional[str] = None
    barcode: Optional[str] = None
    payment_url: Optional[str] = None
    paid_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
