from typing import Optional

"""Invoice model – boletos / payment installments."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum as SAEnum, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin
from app.models.enums import InvoiceStatus


class Invoice(Base, TenantMixin, TimestampMixin):
    """A single payment installment (boleto) linked to a client-lot purchase."""

    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_lot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client_lots.id", ondelete="CASCADE"), nullable=False
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    installment_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(
        SAEnum(InvoiceStatus, name="invoice_status", create_constraint=False),
        default=InvoiceStatus.PENDING,
        nullable=False,
        index=True,
    )
    asaas_payment_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    barcode: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payment_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    client_lot = relationship("ClientLot", back_populates="invoices", lazy="selectin")
    boletos = relationship("Boleto", back_populates="invoice", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Invoice #{self.installment_number} due={self.due_date} status={self.status.value}>"
