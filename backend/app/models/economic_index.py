
"""EconomicIndex model – stores manual and API-fetched economic index values."""

from typing import Optional

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Enum as SAEnum, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin
from app.models.enums import AdjustmentIndex, IndexSource


class EconomicIndex(Base, TenantMixin, TimestampMixin):
    """Stores economic index values (IPCA, IGPM, CUB, INPC) by month."""

    __tablename__ = "economic_indices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    index_type: Mapped[AdjustmentIndex] = mapped_column(
        SAEnum(AdjustmentIndex, name="adjustment_index", create_constraint=False),
        nullable=False,
        index=True,
    )
    state_code: Mapped[Optional[str]] = mapped_column(
        String(2), nullable=True, index=True,
        comment="State code for CUB (e.g. SC, SP). NULL for national indices."
    )
    reference_month: Mapped[date] = mapped_column(
        Date, nullable=False, index=True,
        comment="First day of the reference month (e.g. 2025-01-01)"
    )
    value: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False,
        comment="Index percentage value for the month"
    )
    source: Mapped[IndexSource] = mapped_column(
        SAEnum(IndexSource, name="index_source", create_constraint=False),
        nullable=False, default=IndexSource.MANUAL,
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )

    creator = relationship("Profile", foreign_keys=[created_by], lazy="selectin")

    def __repr__(self) -> str:
        return f"<EconomicIndex {self.index_type.value} {self.reference_month} = {self.value}>"
