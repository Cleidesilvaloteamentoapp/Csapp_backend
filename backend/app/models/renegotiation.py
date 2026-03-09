
"""Renegotiation model – tracks debt renegotiation proposals and outcomes."""

from typing import Optional

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum as SAEnum, ForeignKey, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin
from app.models.enums import RenegotiationStatus


class Renegotiation(Base, TenantMixin, TimestampMixin):
    """A renegotiation proposal for overdue debt on a client contract."""

    __tablename__ = "renegotiations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_lot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client_lots.id", ondelete="CASCADE"), nullable=False, index=True
    )

    status: Mapped[RenegotiationStatus] = mapped_column(
        SAEnum(RenegotiationStatus, name="renegotiation_status", create_constraint=False),
        default=RenegotiationStatus.DRAFT,
        nullable=False,
        index=True,
    )

    # Original debt info
    original_debt_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    overdue_invoices_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    penalty_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    interest_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)

    # Renegotiated terms
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    penalty_waived: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    interest_waived: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    final_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    new_installments: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_due_date: Mapped[date] = mapped_column(Date, nullable=False)

    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # IDs of cancelled invoices/boletos (stored as JSON array)
    cancelled_invoice_ids: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    cancelled_boleto_ids: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    new_invoice_ids: Mapped[Optional[list]] = mapped_column(JSONB, default=list)

    # Approval
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=False
    )

    # Relationships
    client = relationship("Client", lazy="selectin")
    client_lot = relationship("ClientLot", lazy="selectin")
    creator = relationship("Profile", foreign_keys=[created_by], lazy="selectin")
    approver = relationship("Profile", foreign_keys=[approved_by], lazy="selectin")

    def __repr__(self) -> str:
        return f"<Renegotiation {self.id} status={self.status.value}>"
