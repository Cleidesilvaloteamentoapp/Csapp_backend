
"""WhatsApp provider credentials model – stores per-company UAZAPI or Meta Cloud API config.

Each company can have up to one credential per provider type (UAZAPI and/or META),
both can be active simultaneously. One is marked as default for dispatching.

SECURITY: Tokens are stored in the DB and NEVER exposed via API responses.
RLS policies enforce tenant isolation by company_id.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Enum as SAEnum

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin
from app.models.enums import WhatsAppProviderType


class WhatsAppCredential(Base, TenantMixin, TimestampMixin):
    """WhatsApp provider credentials linked to a company (tenant)."""

    __tablename__ = "whatsapp_credentials"
    __table_args__ = (
        UniqueConstraint("company_id", "provider", name="uq_whatsapp_company_provider"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    provider: Mapped[str] = mapped_column(
        SAEnum(WhatsAppProviderType, name="whatsapp_provider_type", create_constraint=False),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- UAZAPI fields (CONFIDENTIAL) ---
    uazapi_base_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    uazapi_instance_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Meta Cloud API fields (CRITICAL) ---
    meta_waba_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    meta_phone_number_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    meta_access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Connection status cache ---
    connection_status: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, default="unknown"
    )
    last_status_check: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationship
    company = relationship("Company", backref="whatsapp_credentials", lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<WhatsAppCredential company={self.company_id} "
            f"provider={self.provider} active={self.is_active}>"
        )
