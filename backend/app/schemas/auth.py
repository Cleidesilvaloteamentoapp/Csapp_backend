from typing import Optional

"""Authentication request / response schemas."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SignupRequest(BaseModel):
    """Register a new company with an initial super_admin user."""

    company_name: str = Field(..., min_length=2, max_length=255)
    company_slug: str = Field(..., min_length=2, max_length=255, pattern=r"^[a-z0-9-]+$")
    full_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    cpf_cnpj: str = Field(..., min_length=11, max_length=20)
    phone: str = Field(..., min_length=10, max_length=20)


class LoginRequest(BaseModel):
    """Email + password login."""

    email: EmailStr
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """JWT token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Refresh token exchange."""

    refresh_token: str


class MeResponse(BaseModel):
    """Current user info."""

    id: UUID
    company_id: Optional[UUID] = None
    role: str
    full_name: str
    email: str
    phone: str
    cpf_cnpj: str

    model_config = ConfigDict(from_attributes=True)
