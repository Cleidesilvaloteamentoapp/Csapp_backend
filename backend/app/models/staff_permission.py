"""StaffPermission model – granular module-level permissions for STAFF users."""

import uuid

from sqlalchemy import Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin


class StaffPermission(Base, TenantMixin, TimestampMixin):
    """One row per STAFF user, containing all permission flags."""

    __tablename__ = "staff_permissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # --- Clients ---
    view_clients: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    manage_clients: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- Lots ---
    view_lots: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    manage_lots: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- Financial / Boletos ---
    view_financial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    manage_financial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- Renegotiations ---
    view_renegotiations: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    manage_renegotiations: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- Rescissions ---
    view_rescissions: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    manage_rescissions: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- Reports (view only – no manage) ---
    view_reports: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- Service Requests ---
    view_service_requests: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    manage_service_requests: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- Documents ---
    view_documents: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    manage_documents: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- Sicredi config ---
    view_sicredi: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    manage_sicredi: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- WhatsApp config ---
    view_whatsapp: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    manage_whatsapp: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- Company financial settings ---
    view_financial_settings: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    manage_financial_settings: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationship back to profile
    profile = relationship("Profile", back_populates="staff_permission", lazy="selectin")

    def __repr__(self) -> str:
        return f"<StaffPermission profile_id={self.profile_id}>"
