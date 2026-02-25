
"""Sicredi API credentials model – stores per-company Sicredi configuration.

Each company can have its own Sicredi Cobrança API credentials,
enabling multi-tenant boleto management where each company manages
its own cooperativa, posto, and beneficiário.

SECURITY: Credentials are stored encrypted at rest via database-level
encryption or application-level encryption. The access_token and
refresh_token are cached here to avoid re-authentication on every request.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin


class SicrediCredential(Base, TenantMixin, TimestampMixin):
    """Sicredi API credentials linked to a company (tenant)."""

    __tablename__ = "sicredi_credentials"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Sicredi API credentials (CONFIDENTIAL – never expose to frontend)
    x_api_key: Mapped[str] = mapped_column(String(100), nullable=False)
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)

    # Cooperativa / Posto / Beneficiário
    cooperativa: Mapped[str] = mapped_column(String(10), nullable=False)
    posto: Mapped[str] = mapped_column(String(10), nullable=False)
    codigo_beneficiario: Mapped[str] = mapped_column(String(20), nullable=False)

    # Environment: "sandbox" or "production"
    environment: Mapped[str] = mapped_column(String(20), nullable=False, default="production")

    # Cached OAuth2 tokens (CRITICAL – never expose)
    access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    refresh_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Webhook contract ID (if registered)
    webhook_contract_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Active flag
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationship
    company = relationship("Company", backref="sicredi_credentials", lazy="selectin")

    def __repr__(self) -> str:
        return f"<SicrediCredential company={self.company_id} cooperativa={self.cooperativa}/{self.posto}>"
