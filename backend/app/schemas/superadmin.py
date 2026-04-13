"""Schemas for superadmin account management."""

import re
import uuid
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class SuperadminCreateRequest(BaseModel):
    """Create a new superadmin user for the same company."""

    full_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    cpf_cnpj: str = Field(..., min_length=11, max_length=20)
    phone: str = Field(..., min_length=10, max_length=20)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[^A-Za-z0-9]", v):
            raise ValueError("Password must contain at least one special character")
        return v


class SuperadminResponse(BaseModel):
    """Superadmin user response."""

    id: uuid.UUID
    company_id: uuid.UUID
    full_name: str
    email: str
    cpf_cnpj: str
    phone: str
    role: str
    is_active: bool

    model_config = {"from_attributes": True}
