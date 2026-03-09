
"""Rescission model – tracks contract termination / distrato process."""

from typing import Optional

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum as SAEnum, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin
from app.models.enums import RescissionStatus


class Rescission(Base, TenantMixin, TimestampMixin):
    """A contract rescission (distrato) for a client lot."""

    __tablename__ = "rescissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_lot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client_lots.id", ondelete="CASCADE"), nullable=False, index=True
    )

    status: Mapped[RescissionStatus] = mapped_column(
        SAEnum(RescissionStatus, name="rescission_status", create_constraint=False),
        default=RescissionStatus.REQUESTED,
        nullable=False,
        index=True,
    )

    reason: Mapped[str] = mapped_column(Text, nullable=False)
    total_paid: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    total_debt: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    penalty_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)

    request_date: Mapped[date] = mapped_column(Date, nullable=False)
    approval_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    completion_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    document_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    requested_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=False
    )
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    client = relationship("Client", lazy="selectin")
    client_lot = relationship("ClientLot", lazy="selectin")
    requester = relationship("Profile", foreign_keys=[requested_by], lazy="selectin")
    approver = relationship("Profile", foreign_keys=[approved_by], lazy="selectin")

    def __repr__(self) -> str:
        return f"<Rescission {self.id} status={self.status.value}>"
