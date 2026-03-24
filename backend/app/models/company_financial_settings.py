
"""CompanyFinancialSettings model – global financial defaults per company."""

from typing import Optional

import uuid
from decimal import Decimal

from sqlalchemy import Enum as SAEnum, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin
from app.models.enums import AdjustmentFrequency, AdjustmentIndex


class CompanyFinancialSettings(Base, TimestampMixin):
    """Global financial defaults for a company.

    One row per company. When a ClientLot doesn't have a specific rate set,
    the system falls back to these values before using hardcoded constants.
    """

    __tablename__ = "company_financial_settings"
    __table_args__ = (
        UniqueConstraint("company_id", name="uq_company_financial_settings_company"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    penalty_rate: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), nullable=False, default=Decimal("0.02"),
        comment="Default penalty rate for overdue invoices (2%)"
    )
    daily_interest_rate: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False, default=Decimal("0.000330"),
        comment="Default daily interest rate (~1%/month = 0.033%/day)"
    )
    adjustment_index: Mapped[AdjustmentIndex] = mapped_column(
        SAEnum(AdjustmentIndex, name="adjustment_index", create_constraint=False),
        nullable=False, default=AdjustmentIndex.IPCA,
        comment="Default price index for contract adjustments"
    )
    adjustment_frequency: Mapped[AdjustmentFrequency] = mapped_column(
        SAEnum(AdjustmentFrequency, name="adjustment_frequency", create_constraint=False),
        nullable=False, default=AdjustmentFrequency.ANNUAL,
        comment="Default frequency for adjustments"
    )
    adjustment_custom_rate: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), nullable=False, default=Decimal("0.05"),
        comment="Default fixed annual rate on top of index (5%)"
    )

    # Relationships
    company = relationship("Company", lazy="selectin")

    def __repr__(self) -> str:
        return f"<CompanyFinancialSettings company={self.company_id}>"
