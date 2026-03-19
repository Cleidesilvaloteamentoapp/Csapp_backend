
"""EarlyPayoffRequest model – client request to pay off contract early."""

from typing import Optional

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin
from app.models.enums import EarlyPayoffStatus


class EarlyPayoffRequest(Base, TenantMixin, TimestampMixin):
    """A client's request to anticipate / pay off their contract."""

    __tablename__ = "early_payoff_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    client_lot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client_lots.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    status: Mapped[EarlyPayoffStatus] = mapped_column(
        SAEnum(EarlyPayoffStatus, name="early_payoff_status", create_constraint=False),
        default=EarlyPayoffStatus.PENDING,
        nullable=False,
        index=True,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
        nullable=False,
    )
    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    client_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Optional message from the client"
    )

    # Relationships
    client = relationship("Client", lazy="selectin")
    client_lot = relationship("ClientLot", lazy="selectin")

    def __repr__(self) -> str:
        return f"<EarlyPayoffRequest client={self.client_id} status={self.status.value}>"
