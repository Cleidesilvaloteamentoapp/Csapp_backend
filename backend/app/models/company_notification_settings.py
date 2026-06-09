
"""Per-company WhatsApp notification preferences.

One row per company (unique on company_id). Created on-demand with all
toggles enabled by default (preserves current behaviour).
"""

import uuid
from typing import Optional

from sqlalchemy import Boolean, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin


class CompanyNotificationSettings(Base, TenantMixin, TimestampMixin):
    """WhatsApp/notification preferences per company."""

    __tablename__ = "company_notification_settings"
    __table_args__ = (
        UniqueConstraint("company_id", name="uq_notif_settings_company"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ---- Client-facing toggles ----
    notify_client_new_boleto: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_client_due_reminder: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_client_overdue: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_client_service: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # ---- Admin-facing toggles ----
    notify_admin_client_created: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_admin_client_deleted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_admin_boleto_generated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_admin_boleto_cancelled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_admin_cycle_request: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # ---- Admin WhatsApp numbers (comma-separated, international format) ----
    admin_whatsapp_numbers: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def get_admin_numbers(self) -> list[str]:
        if not self.admin_whatsapp_numbers:
            return []
        return [n.strip() for n in self.admin_whatsapp_numbers.split(",") if n.strip()]

    def __repr__(self) -> str:
        return f"<CompanyNotificationSettings company={self.company_id}>"
