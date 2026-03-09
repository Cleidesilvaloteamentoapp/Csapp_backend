
"""Renegotiation schemas (Pydantic v2)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional, Dict, List
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RenegotiationCreate(BaseModel):
    """Payload to create a renegotiation proposal."""

    client_id: UUID
    client_lot_id: UUID
    discount_amount: Decimal = Field(Decimal("0"), ge=0)
    penalty_waived: Decimal = Field(Decimal("0"), ge=0)
    interest_waived: Decimal = Field(Decimal("0"), ge=0)
    new_installments: int = Field(1, ge=1, le=360)
    first_due_date: date
    reason: Optional[str] = None
    admin_notes: Optional[str] = None


class RenegotiationApprove(BaseModel):
    """Payload to approve or reject a renegotiation."""

    approved: bool
    admin_notes: Optional[str] = None


class RenegotiationResponse(BaseModel):
    """Renegotiation read response."""

    id: UUID
    company_id: UUID
    client_id: UUID
    client_lot_id: UUID
    status: str

    original_debt_amount: Decimal
    overdue_invoices_count: int
    penalty_amount: Decimal
    interest_amount: Decimal

    discount_amount: Decimal
    penalty_waived: Decimal
    interest_waived: Decimal
    final_amount: Decimal
    new_installments: int
    first_due_date: date

    reason: Optional[str] = None
    admin_notes: Optional[str] = None

    cancelled_invoice_ids: Optional[List[Any]] = None
    cancelled_boleto_ids: Optional[List[Any]] = None
    new_invoice_ids: Optional[List[Any]] = None

    approved_by: Optional[UUID] = None
    approved_at: Optional[datetime] = None
    applied_at: Optional[datetime] = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
