from typing import Optional

"""Notification model – in-app notifications for users."""

import uuid

from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin
from app.models.enums import NotificationType


class Notification(Base, TenantMixin, TimestampMixin):
    """An in-app notification delivered to a specific user."""

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[NotificationType] = mapped_column(
        SAEnum(NotificationType, name="notification_type", create_constraint=False),
        default=NotificationType.GERAL,
        nullable=False,
        index=True,
    )
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    data: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    # Relationships
    user = relationship("Profile", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Notification {self.type.value} user={self.user_id} read={self.is_read}>"
