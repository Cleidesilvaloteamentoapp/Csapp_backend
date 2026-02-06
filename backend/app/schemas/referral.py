from typing import Optional

"""Referral schemas (Pydantic v2)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ReferralCreate(BaseModel):
    """Payload for creating a referral."""

    referred_name: str = Field(..., min_length=2, max_length=255)
    referred_phone: str = Field(..., min_length=10, max_length=20)
    referred_email: Optional[EmailStr] = None


class ReferralResponse(BaseModel):
    """Referral read response."""

    id: UUID
    company_id: UUID
    referrer_client_id: UUID
    referred_name: str
    referred_phone: str
    referred_email: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
