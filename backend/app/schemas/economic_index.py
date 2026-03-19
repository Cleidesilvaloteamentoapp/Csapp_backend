
"""Economic index schemas (Pydantic v2)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EconomicIndexCreate(BaseModel):
    """Payload for manually creating an economic index entry."""

    index_type: str = Field(..., pattern="^(IPCA|IGPM|CUB|INPC)$")
    state_code: Optional[str] = Field(None, min_length=2, max_length=2, description="State code for CUB (e.g. SC, SP)")
    reference_month: date = Field(..., description="First day of the reference month (e.g. 2025-01-01)")
    value: Decimal = Field(..., description="Index percentage value for the month")


class EconomicIndexUpdate(BaseModel):
    """Payload for updating an economic index entry."""

    value: Optional[Decimal] = None
    state_code: Optional[str] = Field(None, min_length=2, max_length=2)


class EconomicIndexResponse(BaseModel):
    """Economic index read response."""

    id: UUID
    company_id: UUID
    index_type: str
    state_code: Optional[str] = None
    reference_month: date
    value: Decimal
    source: str
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
