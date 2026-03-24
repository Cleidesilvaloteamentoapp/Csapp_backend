
"""Pydantic v2 schemas for WhatsApp provider management."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Credential schemas
# ---------------------------------------------------------------------------

class WhatsAppCredentialCreate(BaseModel):
    """Create a new WhatsApp credential."""

    provider: str = Field(..., description="UAZAPI or META")

    # UAZAPI fields
    uazapi_base_url: Optional[str] = Field(None, max_length=500)
    uazapi_instance_token: Optional[str] = None

    # Meta fields
    meta_waba_id: Optional[str] = Field(None, max_length=100)
    meta_phone_number_id: Optional[str] = Field(None, max_length=100)
    meta_access_token: Optional[str] = None

    is_default: bool = False

    @model_validator(mode="after")
    def validate_provider_fields(self) -> "WhatsAppCredentialCreate":
        if self.provider == "UAZAPI":
            if not self.uazapi_base_url or not self.uazapi_instance_token:
                raise ValueError("UAZAPI requires uazapi_base_url and uazapi_instance_token")
        elif self.provider == "META":
            if not self.meta_waba_id or not self.meta_phone_number_id or not self.meta_access_token:
                raise ValueError("META requires meta_waba_id, meta_phone_number_id, and meta_access_token")
        else:
            raise ValueError("provider must be UAZAPI or META")
        return self


class WhatsAppCredentialUpdate(BaseModel):
    """Update an existing WhatsApp credential."""

    uazapi_base_url: Optional[str] = Field(None, max_length=500)
    uazapi_instance_token: Optional[str] = None
    meta_waba_id: Optional[str] = Field(None, max_length=100)
    meta_phone_number_id: Optional[str] = Field(None, max_length=100)
    meta_access_token: Optional[str] = None
    is_active: Optional[bool] = None


class WhatsAppCredentialResponse(BaseModel):
    """Public representation of a WhatsApp credential (tokens hidden)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    provider: str
    is_active: bool
    is_default: bool

    # UAZAPI – show base_url only, hide token
    uazapi_base_url: Optional[str] = None

    # Meta – show waba_id and phone_number_id, hide access_token
    meta_waba_id: Optional[str] = None
    meta_phone_number_id: Optional[str] = None

    # Connection status cache
    connection_status: Optional[str] = None
    last_status_check: Optional[datetime] = None

    created_at: datetime
    updated_at: datetime

    @property
    def has_token(self) -> bool:
        if self.provider == "UAZAPI":
            return self.uazapi_base_url is not None
        return self.meta_waba_id is not None


# ---------------------------------------------------------------------------
# Connection status
# ---------------------------------------------------------------------------

class ConnectionStatusResponse(BaseModel):
    """Result of a connection status check."""

    connected: bool
    status: str
    profile_name: Optional[str] = None
    phone_number: Optional[str] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Test message
# ---------------------------------------------------------------------------

class WhatsAppTestMessage(BaseModel):
    """Send a test message."""

    to: str = Field(..., description="Phone number in international format (e.g. 5511999999999)")
    body: str = Field(..., min_length=1, max_length=4096)
    credential_id: Optional[UUID] = Field(None, description="Specific credential to use. If empty, uses default.")


# ---------------------------------------------------------------------------
# Template schemas (Meta only)
# ---------------------------------------------------------------------------

class WhatsAppTemplateCreate(BaseModel):
    """Create a new WhatsApp message template (Meta Cloud API)."""

    name: str = Field(..., min_length=1, max_length=512, pattern=r"^[a-z0-9_]+$")
    language: str = Field(default="pt_BR")
    category: str = Field(..., description="UTILITY, MARKETING, or AUTHENTICATION")
    components: list[dict[str, Any]] = Field(
        ...,
        description="Template components following Meta's format",
    )

    @model_validator(mode="after")
    def validate_category(self) -> "WhatsAppTemplateCreate":
        valid = {"UTILITY", "MARKETING", "AUTHENTICATION"}
        if self.category not in valid:
            raise ValueError(f"category must be one of {valid}")
        return self


class WhatsAppTemplateResponse(BaseModel):
    """Public template info."""

    id: Optional[str] = None
    name: str
    status: str
    category: str = ""
    language: str = "pt_BR"
    components: list[dict[str, Any]] = []


class WhatsAppTemplateList(BaseModel):
    """Paginated template list."""

    templates: list[WhatsAppTemplateResponse]
    count: int
