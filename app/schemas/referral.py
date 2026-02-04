from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from app.models.enums import ReferralStatus


class ReferralCreate(BaseModel):
    referred_name: str = Field(..., min_length=2, max_length=100)
    referred_phone: str = Field(..., min_length=10, max_length=20)
    referred_email: Optional[EmailStr] = None


class ReferralUpdate(BaseModel):
    status: Optional[ReferralStatus] = None


class ReferralResponse(BaseModel):
    id: str
    referrer_client_id: str
    referred_name: str
    referred_phone: str
    referred_email: Optional[str] = None
    status: ReferralStatus
    created_at: datetime
