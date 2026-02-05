"""Company schemas (Pydantic v2)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CompanyCreate(BaseModel):
    """Payload for creating a new company (super_admin)."""

    name: str = Field(..., min_length=2, max_length=255)
    slug: str = Field(..., min_length=2, max_length=255, pattern=r"^[a-z0-9-]+$")
    settings: dict[str, Any] | None = None


class CompanyUpdate(BaseModel):
    """Payload for updating an existing company."""

    name: str | None = Field(None, min_length=2, max_length=255)
    slug: str | None = Field(None, min_length=2, max_length=255, pattern=r"^[a-z0-9-]+$")
    settings: dict[str, Any] | None = None


class CompanyStatusUpdate(BaseModel):
    """Activate or suspend a company."""

    status: str = Field(..., pattern=r"^(active|suspended|inactive)$")


class CompanyResponse(BaseModel):
    """Company read response."""

    id: UUID
    name: str
    slug: str
    settings: dict[str, Any] | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
