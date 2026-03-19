
"""CycleApproval model – tracks admin approval for generating next 12-installment cycle."""

from typing import Optional

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin
from app.models.enums import CycleApprovalStatus


class CycleApproval(Base, TenantMixin, TimestampMixin):
    """Approval request for generating the next 12-installment cycle."""

    __tablename__ = "cycle_approvals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_lot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client_lots.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[CycleApprovalStatus] = mapped_column(
        SAEnum(CycleApprovalStatus, name="cycle_approval_status", create_constraint=False),
        default=CycleApprovalStatus.PENDING,
        nullable=False,
        index=True,
    )
    previous_installment_value: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False,
    )
    new_installment_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2), nullable=True,
        comment="Calculated new value after adjustment; set on approval"
    )
    adjustment_details: Mapped[Optional[dict]] = mapped_column(
        JSONB, default=dict,
        comment="IPCA/IGPM %, fixed rate %, adjustment breakdown"
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
        nullable=False,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True,
    )
    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    client_lot = relationship("ClientLot", lazy="selectin")
    approver = relationship("Profile", foreign_keys=[approved_by], lazy="selectin")

    def __repr__(self) -> str:
        return f"<CycleApproval lot={self.client_lot_id} cycle={self.cycle_number} status={self.status.value}>"
