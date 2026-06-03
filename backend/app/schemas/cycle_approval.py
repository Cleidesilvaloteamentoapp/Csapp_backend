
"""Cycle approval schemas (Pydantic v2)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.lot import EffectiveRatesResponse


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
    """Cycle approval enriched with the data the admin needs to review/edit.

    Highlights the rates currently applied + the previous cycle's adjustment so
    the admin can review them before approving the new (suggested) value.
    """

    client_name: Optional[str] = None
    lot_identifier: Optional[str] = None
    total_installments: Optional[int] = None

    # Effective rates currently applied to the contract (per-lot → company → default).
    effective_rates: Optional[EffectiveRatesResponse] = None
    last_adjustment_date: Optional[date] = None
    # The previously applied adjustment breakdown (for review/comparison).
    previous_adjustment_details: Optional[dict] = None
    # Server-computed suggestion: IPCA accumulated + fixed rate applied to the current value.
    suggested_new_value: Optional[Decimal] = None
    suggested_adjustment_details: Optional[dict] = None
    # Cycle debit: how many installments remain and how many this cycle will generate.
    remaining_installments: Optional[int] = None
    installments_to_generate: Optional[int] = None


class CycleApproveRequest(BaseModel):
    """Request to approve a cycle and set new installment value."""

    new_installment_value: Decimal = Field(..., gt=0, description="New installment value after adjustment")
    adjustment_details: Optional[dict] = Field(None, description="Breakdown: index %, fixed rate %, etc.")
    admin_notes: Optional[str] = Field(None, max_length=500)


class CycleRejectRequest(BaseModel):
    """Request to reject a cycle approval."""

    admin_notes: str = Field(..., min_length=5, max_length=500, description="Reason for rejection")
