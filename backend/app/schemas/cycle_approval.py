
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

    # Settlement snapshot taken when the renewal was raised. The panel shows the
    # cycle ahead of its last due date, so it has to say what is still open.
    unpaid_count: int = 0
    overdue_amount: Decimal = Decimal("0")
    is_final_cycle: bool = False

    # Forced renewal: released despite open installments.
    forced: bool = False
    forced_reason: Optional[str] = None
    forced_by: Optional[UUID] = None

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

    # Live settlement of the closing cycle, recomputed on read so the panel
    # reflects payments that landed after the renewal was raised.
    cycle_installments: Optional[int] = None
    cycle_settled: Optional[int] = None
    cycle_unpaid: Optional[int] = None
    cycle_overdue_amount: Optional[Decimal] = None
    can_approve: bool = True
    blocked_reason: Optional[str] = None


class CycleApproveRequest(BaseModel):
    """Request to approve a cycle and set new installment value."""

    new_installment_value: Decimal = Field(..., gt=0, description="New installment value after adjustment")
    adjustment_details: Optional[dict] = Field(None, description="Breakdown: index %, fixed rate %, etc.")
    admin_notes: Optional[str] = Field(None, max_length=500)


class CycleRejectRequest(BaseModel):
    """Request to reject a cycle approval."""

    admin_notes: str = Field(..., min_length=5, max_length=500, description="Reason for rejection")


class CycleForceApproveRequest(CycleApproveRequest):
    """Release the next cycle despite installments still open.

    The justification is mandatory and stored on the approval: this is the one
    path that bills a client for a new cycle while the previous one is unpaid,
    so it has to be answerable afterwards.
    """

    justification: str = Field(
        ...,
        min_length=20,
        max_length=1000,
        description="Why the renewal is being released with open installments",
    )


class CycleRequestRequest(BaseModel):
    """Open a renewal for a contract before the scheduled trigger raises it."""

    client_lot_id: UUID
    admin_notes: Optional[str] = Field(None, max_length=500)


class CyclePendingCountResponse(BaseModel):
    """Cheap counters for the sidebar badge and the dashboard action queue."""

    pending: int = 0
    final_cycle: int = 0
    blocked_by_unpaid: int = 0


class DeedChecklistItem(BaseModel):
    document_type: str
    label: str
    done: bool = False
    note: Optional[str] = None
    updated_at: Optional[datetime] = None


class DeedChecklistResponse(BaseModel):
    """Escrituração checklist for a contract on its final cycle."""

    id: UUID
    client_lot_id: UUID
    items: list[DeedChecklistItem] = []
    notes: Optional[str] = None
    completed_at: Optional[datetime] = None
    # Resolved against the documents the client already uploaded.
    uploaded_document_types: list[str] = []

    model_config = ConfigDict(from_attributes=True)


class DeedChecklistUpdate(BaseModel):
    """Toggle one checklist item, or replace the free-text notes."""

    document_type: Optional[str] = None
    done: Optional[bool] = None
    note: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = Field(None, max_length=2000)
