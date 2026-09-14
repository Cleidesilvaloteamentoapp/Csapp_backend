
"""CompanyBranding model – per-company visual identity (white-label).

One row per company (unique on company_id). Every column is nullable: a NULL
value means "fall back to the platform default", which lives in the frontend's
``globals.css``. Only the seed colours are stored – the remaining ~28 design
tokens are derived from them on the client.
"""

import uuid
from typing import Optional

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin


class CompanyBranding(Base, TenantMixin, TimestampMixin):
    """Visual identity overrides for a company."""

    __tablename__ = "company_branding"
    __table_args__ = (
        UniqueConstraint("company_id", name="uq_company_branding_company"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ---- Seed colours (#RRGGBB) ----
    primary_color: Mapped[Optional[str]] = mapped_column(
        String(7), nullable=True, comment="Brand colour: buttons, links, charts"
    )
    accent_color: Mapped[Optional[str]] = mapped_column(
        String(7), nullable=True, comment="Highlight colour: focus ring, sidebar mark"
    )
    sidebar_color: Mapped[Optional[str]] = mapped_column(
        String(7), nullable=True, comment="Sidebar background"
    )
    background_color: Mapped[Optional[str]] = mapped_column(
        String(7), nullable=True, comment="App background"
    )
    success_color: Mapped[Optional[str]] = mapped_column(
        String(7), nullable=True, comment="Positive state colour"
    )

    # ---- Shape ----
    radius: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True, comment="Base border radius, e.g. '0.625rem'"
    )

    # ---- Assets (Supabase Storage paths, never URLs) ----
    logo_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    favicon_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    app_icon_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ---- Wording ----
    display_name: Mapped[Optional[str]] = mapped_column(
        String(60), nullable=True, comment="Replaces the 'CSApp' wordmark"
    )
    tagline: Mapped[Optional[str]] = mapped_column(
        String(80), nullable=True, comment="Replaces 'Loteamentos' under the wordmark"
    )

    # Relationships
    company = relationship("Company", lazy="selectin")

    def __repr__(self) -> str:
        return f"<CompanyBranding company={self.company_id}>"
