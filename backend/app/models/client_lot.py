from typing import Optional

"""ClientLot model – relationship between a client and a purchased lot."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, Enum as SAEnum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin
from app.models.enums import AdjustmentFrequency, AdjustmentIndex, ClientLotStatus


class ClientLot(Base, TenantMixin, TimestampMixin):
    """Records a lot purchase by a client, including payment plan."""

    __tablename__ = "client_lots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    lot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lots.id", ondelete="CASCADE"), nullable=False
    )
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    down_payment: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True, default=0)
    total_installments: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    paid_installments: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=0,
        comment="Manual count of paid installments for legacy clients (before system tracking)"
    )
    current_cycle: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    current_installment_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    annual_adjustment_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 4), nullable=True, default=Decimal("0.05"),
        comment="Fixed annual rate (default 5%) added on top of IPCA"
    )
    last_adjustment_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    last_cycle_paid_at: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True,
        comment="Date when last 12-installment cycle was fully paid"
    )
    penalty_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 4), nullable=True,
        comment="Custom penalty rate overriding system default 0.02 (2%)"
    )
    daily_interest_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(8, 6), nullable=True,
        comment="Custom daily interest rate overriding default 0.00033"
    )
    adjustment_index: Mapped[Optional[AdjustmentIndex]] = mapped_column(
        SAEnum(AdjustmentIndex, name="adjustment_index", create_constraint=False),
        nullable=True,
        comment="Price index for adjustments: IPCA, IGPM, CUB, INPC"
    )
    adjustment_frequency: Mapped[Optional[AdjustmentFrequency]] = mapped_column(
        SAEnum(AdjustmentFrequency, name="adjustment_frequency", create_constraint=False),
        nullable=True, default=AdjustmentFrequency.ANNUAL,
        comment="How often adjustments are applied"
    )
    adjustment_custom_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 4), nullable=True,
        comment="Custom fixed rate overriding default 5% annual"
    )
    previous_client_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True,
        comment="Previous owner after a contract transfer"
    )
    transfer_date: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True,
        comment="Date of the last ownership transfer"
    )
    payment_plan: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    status: Mapped[ClientLotStatus] = mapped_column(
        SAEnum(ClientLotStatus, name="client_lot_status", create_constraint=False),
        default=ClientLotStatus.ACTIVE,
        nullable=False,
        index=True,
    )

    # Relationships
    client = relationship(
        "Client", back_populates="client_lots", lazy="selectin",
        foreign_keys=[client_id],
    )
    previous_client = relationship(
        "Client", lazy="selectin",
        foreign_keys=[previous_client_id],
    )
    lot = relationship("Lot", back_populates="client_lots", lazy="selectin")
    invoices = relationship("Invoice", back_populates="client_lot", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ClientLot client={self.client_id} lot={self.lot_id}>"
