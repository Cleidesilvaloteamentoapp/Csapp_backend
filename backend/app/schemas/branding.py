"""Pydantic schemas for per-company branding (white-label)."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

HEX_COLOR = r"^#[0-9A-Fa-f]{6}$"
# e.g. "0.625rem", "8px", "0" — a plain CSS length
RADIUS = r"^\d+(\.\d+)?(rem|px|em)?$"


class BrandingUpdate(BaseModel):
    """Partial update. Omitted fields keep their value; explicit ``null`` clears
    the override so the company falls back to the platform default."""

    primary_color: Optional[str] = Field(None, pattern=HEX_COLOR)
    accent_color: Optional[str] = Field(None, pattern=HEX_COLOR)
    sidebar_color: Optional[str] = Field(None, pattern=HEX_COLOR)
    background_color: Optional[str] = Field(None, pattern=HEX_COLOR)
    success_color: Optional[str] = Field(None, pattern=HEX_COLOR)

    radius: Optional[str] = Field(None, pattern=RADIUS)

    display_name: Optional[str] = Field(None, max_length=60)
    tagline: Optional[str] = Field(None, max_length=80)


class BrandingResponse(BaseModel):
    """Branding as consumed by the frontend.

    Asset *paths* are never exposed; they are replaced by stable public URLs
    served by ``GET /branding/public/{slug}/{kind}``.
    """

    model_config = ConfigDict(from_attributes=True)

    company_id: UUID
    company_slug: str

    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    sidebar_color: Optional[str] = None
    background_color: Optional[str] = None
    success_color: Optional[str] = None

    radius: Optional[str] = None

    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    app_icon_url: Optional[str] = None

    display_name: Optional[str] = None
    tagline: Optional[str] = None

    updated_at: Optional[datetime] = None
