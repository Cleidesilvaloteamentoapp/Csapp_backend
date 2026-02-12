from typing import Optional

"""Lot model – individual lots within developments."""

import uuid
from decimal import Decimal

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin
from app.models.enums import LotStatus


class Lot(Base, TenantMixin, TimestampMixin):
    """An individual lot in a development."""

    __tablename__ = "lots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    development_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("developments.id", ondelete="CASCADE"), nullable=False
    )
    lot_number: Mapped[str] = mapped_column(String(50), nullable=False)
    block: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    area_m2: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[LotStatus] = mapped_column(
        SAEnum(LotStatus, name="lot_status", create_constraint=False),
        default=LotStatus.AVAILABLE,
        nullable=False,
        index=True,
    )
    documents: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    # Relationships
    development = relationship("Development", back_populates="lots", lazy="selectin")
    client_lots = relationship("ClientLot", back_populates="lot", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Lot {self.lot_number} block={self.block}>"
