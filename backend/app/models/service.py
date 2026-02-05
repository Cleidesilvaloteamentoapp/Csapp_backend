"""Service models – service types and service orders."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, Enum as SAEnum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin
from app.models.enums import ServiceOrderStatus


class ServiceType(Base, TenantMixin, TimestampMixin):
    """Catalogue of services offered by a company."""

    __tablename__ = "service_types"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    orders = relationship("ServiceOrder", back_populates="service_type", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ServiceType {self.name}>"


class ServiceOrder(Base, TenantMixin, TimestampMixin):
    """An order for a service requested by a client."""

    __tablename__ = "service_orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    lot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lots.id", ondelete="SET NULL"), nullable=True
    )
    service_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("service_types.id", ondelete="CASCADE"), nullable=False
    )
    requested_date: Mapped[date] = mapped_column(Date, nullable=False)
    execution_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[ServiceOrderStatus] = mapped_column(
        SAEnum(ServiceOrderStatus, name="service_order_status", create_constraint=True),
        default=ServiceOrderStatus.REQUESTED,
        nullable=False,
        index=True,
    )
    cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    client = relationship("Client", lazy="selectin")
    lot = relationship("Lot", lazy="selectin")
    service_type = relationship("ServiceType", back_populates="orders", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ServiceOrder {self.id} status={self.status.value}>"
