
"""Company schemas (Pydantic v2)."""

from datetime import datetime
from typing import Any, Optional, Dict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CompanyCreate(BaseModel):
    """Payload for creating a new company (super_admin)."""

    name: str = Field(..., min_length=2, max_length=255)
    slug: str = Field(..., min_length=2, max_length=255, pattern=r"^[a-z0-9-]+$")
    settings: Optional[Dict[str, Any]] = None


class CompanyUpdate(BaseModel):
    """Payload for updating an existing company."""

    name: Optional[str] = Field(None, min_length=2, max_length=255)
    slug: Optional[str] = Field(None, min_length=2, max_length=255, pattern=r"^[a-z0-9-]+$")
    settings: Optional[Dict[str, Any]] = None


class CompanyStatusUpdate(BaseModel):
    """Activate or suspend a company."""

    status: str = Field(..., pattern=r"^(active|suspended|inactive)$")


class CompanyResponse(BaseModel):
    """Company read response."""

    id: UUID
    name: str
    slug: str
    settings: Optional[Dict[str, Any]] = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
