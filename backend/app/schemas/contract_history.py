
"""ContractHistory schemas (Pydantic v2)."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional, Dict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ContractHistoryResponse(BaseModel):
    """Contract history event read response."""

    id: UUID
    company_id: UUID
    client_id: UUID
    client_lot_id: Optional[UUID] = None
    invoice_id: Optional[UUID] = None
    boleto_id: Optional[UUID] = None
    event_type: str
    description: str
    amount: Optional[Decimal] = None
    previous_value: Optional[str] = None
    new_value: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None
    performed_by: Optional[UUID] = None
    ip_address: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContractHistoryCreate(BaseModel):
    """Payload for manually adding a contract history note."""

    client_id: UUID
    client_lot_id: Optional[UUID] = None
    event_type: str = Field("NOTE", pattern=r"^(NOTE|STATUS_CHANGE|MANUAL_WRITEOFF)$")
    description: str = Field(..., min_length=1, max_length=2000)
    amount: Optional[Decimal] = None
    metadata_json: Optional[Dict[str, Any]] = None
