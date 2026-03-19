
"""ContractTransfer model – tracks ownership transfer of a contract/lot between clients."""

from typing import Optional

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Enum as SAEnum, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin
from app.models.enums import TransferStatus


class ContractTransfer(Base, TenantMixin, TimestampMixin):
    """Records a contract/lot transfer from one client to another."""

    __tablename__ = "contract_transfers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_lot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client_lots.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    from_client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    to_client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    status: Mapped[TransferStatus] = mapped_column(
        SAEnum(TransferStatus, name="transfer_status", create_constraint=False),
        default=TransferStatus.PENDING,
        nullable=False,
        index=True,
    )
    transfer_fee: Mapped[Optional[Numeric]] = mapped_column(
        Numeric(14, 2), nullable=True, default=0,
        comment="Fee charged for the transfer"
    )
    transfer_date: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True,
        comment="Effective date of the transfer"
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    documents: Mapped[Optional[dict]] = mapped_column(
        JSONB, default=list,
        comment="List of document paths (signed terms, fee receipts)"
    )

    requested_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=False,
    )
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Relationships
    client_lot = relationship("ClientLot", lazy="selectin")
    from_client = relationship("Client", foreign_keys=[from_client_id], lazy="selectin")
    to_client = relationship("Client", foreign_keys=[to_client_id], lazy="selectin")
    requester = relationship("Profile", foreign_keys=[requested_by], lazy="selectin")
    approver = relationship("Profile", foreign_keys=[approved_by], lazy="selectin")

    def __repr__(self) -> str:
        return f"<ContractTransfer {self.from_client_id} -> {self.to_client_id} status={self.status.value}>"
