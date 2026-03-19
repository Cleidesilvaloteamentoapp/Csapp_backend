
"""Early payoff request schemas (Pydantic v2)."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EarlyPayoffCreate(BaseModel):
    """Payload for client to request early payoff."""

    client_lot_id: UUID
    client_message: Optional[str] = Field(None, max_length=500, description="Optional message from the client")


class EarlyPayoffResponse(BaseModel):
    """Early payoff request read response."""

    id: UUID
    company_id: UUID
    client_id: UUID
    client_lot_id: UUID
    status: str
    requested_at: datetime
    admin_notes: Optional[str] = None
    client_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EarlyPayoffAdminUpdate(BaseModel):
    """Admin update for early payoff request."""

    status: str = Field(..., pattern="^(CONTACTED|COMPLETED|CANCELLED)$")
    admin_notes: Optional[str] = Field(None, max_length=500)
