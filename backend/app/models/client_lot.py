from typing import Optional

"""ClientLot model – relationship between a client and a purchased lot."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Enum as SAEnum, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin
from app.models.enums import ClientLotStatus


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
    payment_plan: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    status: Mapped[ClientLotStatus] = mapped_column(
        SAEnum(ClientLotStatus, name="client_lot_status", create_constraint=True),
        default=ClientLotStatus.ACTIVE,
        nullable=False,
        index=True,
    )

    # Relationships
    client = relationship("Client", back_populates="client_lots", lazy="selectin")
    lot = relationship("Lot", back_populates="client_lots", lazy="selectin")
    invoices = relationship("Invoice", back_populates="client_lot", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ClientLot client={self.client_id} lot={self.lot_id}>"
