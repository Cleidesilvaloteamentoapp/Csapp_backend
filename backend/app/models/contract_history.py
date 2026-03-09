
"""ContractHistory model – tracks all events/movements for a client contract."""

from typing import Optional

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin
from app.models.enums import ContractEventType


class ContractHistory(Base, TenantMixin):
    """Immutable record of a contract event (payment, overdue, renegotiation, etc.)."""

    __tablename__ = "contract_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_lot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client_lots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True
    )
    boleto_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("boletos.id", ondelete="SET NULL"), nullable=True
    )

    event_type: Mapped[ContractEventType] = mapped_column(
        SAEnum(ContractEventType, name="contract_event_type", create_constraint=False),
        nullable=False,
        index=True,
    )

    description: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    previous_value: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    performed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
        nullable=False,
    )

    # Relationships
    client = relationship("Client", lazy="selectin")
    client_lot = relationship("ClientLot", lazy="selectin")
    invoice = relationship("Invoice", lazy="selectin")
    boleto = relationship("Boleto", lazy="selectin")
    performer = relationship("Profile", foreign_keys=[performed_by], lazy="selectin")

    def __repr__(self) -> str:
        return f"<ContractHistory {self.event_type.value} client={self.client_id}>"
