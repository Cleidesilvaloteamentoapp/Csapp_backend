
"""Rescission schemas (Pydantic v2)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional, Dict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RescissionCreate(BaseModel):
    """Payload to request a contract rescission (distrato)."""

    client_id: UUID
    client_lot_id: UUID
    reason: str = Field(..., min_length=5, max_length=2000)
    admin_notes: Optional[str] = None


class RescissionApprove(BaseModel):
    """Payload to approve or reject a rescission."""

    approved: bool
    refund_amount: Decimal = Field(Decimal("0"), ge=0)
    penalty_amount: Decimal = Field(Decimal("0"), ge=0)
    admin_notes: Optional[str] = None


class RescissionResponse(BaseModel):
    """Rescission read response."""

    id: UUID
    company_id: UUID
    client_id: UUID
    client_lot_id: UUID
    status: str

    reason: str
    total_paid: Decimal
    total_debt: Decimal
    refund_amount: Decimal
    penalty_amount: Decimal

    request_date: date
    approval_date: Optional[date] = None
    completion_date: Optional[date] = None

    admin_notes: Optional[str] = None
    document_path: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None

    requested_by: UUID
    approved_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
