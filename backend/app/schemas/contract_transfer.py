
"""Contract transfer schemas (Pydantic v2)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ContractTransferCreate(BaseModel):
    """Payload for creating a contract transfer request."""

    client_lot_id: UUID
    from_client_id: UUID
    to_client_id: UUID
    transfer_fee: Optional[Decimal] = Field(None, ge=0)
    reason: Optional[str] = Field(None, max_length=500)


class ContractTransferResponse(BaseModel):
    """Contract transfer read response."""

    id: UUID
    company_id: UUID
    client_lot_id: UUID
    from_client_id: UUID
    to_client_id: UUID
    status: str
    transfer_fee: Optional[Decimal] = None
    transfer_date: Optional[date] = None
    reason: Optional[str] = None
    admin_notes: Optional[str] = None
    documents: Optional[list] = None
    requested_by: UUID
    approved_by: Optional[UUID] = None
    approved_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContractTransferDetailResponse(ContractTransferResponse):
    """Transfer with client names for admin views."""

    from_client_name: Optional[str] = None
    to_client_name: Optional[str] = None
    lot_identifier: Optional[str] = None


class ContractTransferApproveRequest(BaseModel):
    """Request to approve a transfer."""

    admin_notes: Optional[str] = Field(None, max_length=500)
    transfer_date: Optional[date] = None


class ContractTransferCompleteRequest(BaseModel):
    """Request to complete an approved transfer."""

    admin_notes: Optional[str] = Field(None, max_length=500)
