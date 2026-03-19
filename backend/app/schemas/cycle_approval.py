
"""Cycle approval schemas (Pydantic v2)."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CycleApprovalResponse(BaseModel):
    """Cycle approval read response."""

    id: UUID
    company_id: UUID
    client_lot_id: UUID
    cycle_number: int
    status: str
    previous_installment_value: Decimal
    new_installment_value: Optional[Decimal] = None
    adjustment_details: Optional[dict] = None
    requested_at: datetime
    approved_at: Optional[datetime] = None
    approved_by: Optional[UUID] = None
    admin_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CycleApprovalWithClientResponse(CycleApprovalResponse):
    """Cycle approval with client lot and client info."""

    client_name: Optional[str] = None
    lot_identifier: Optional[str] = None
    total_installments: Optional[int] = None


class CycleApproveRequest(BaseModel):
    """Request to approve a cycle and set new installment value."""

    new_installment_value: Decimal = Field(..., gt=0, description="New installment value after adjustment")
    adjustment_details: Optional[dict] = Field(None, description="Breakdown: index %, fixed rate %, etc.")
    admin_notes: Optional[str] = Field(None, max_length=500)


class CycleRejectRequest(BaseModel):
    """Request to reject a cycle approval."""

    admin_notes: str = Field(..., min_length=5, max_length=500, description="Reason for rejection")
