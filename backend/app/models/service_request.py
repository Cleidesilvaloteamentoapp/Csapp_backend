from typing import Optional

"""ServiceRequest + ServiceRequestMessage models – client support ticket system."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin
from app.models.enums import (
    ServiceRequestPriority,
    ServiceRequestStatus,
    ServiceRequestType,
)


class ServiceRequest(Base, TenantMixin, TimestampMixin):
    """A support ticket opened by a client."""

    __tablename__ = "service_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticket_number: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    service_type: Mapped[ServiceRequestType] = mapped_column(
        SAEnum(ServiceRequestType, name="service_request_type", create_constraint=False),
        nullable=False,
        index=True,
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ServiceRequestStatus] = mapped_column(
        SAEnum(ServiceRequestStatus, name="service_request_status", create_constraint=False),
        default=ServiceRequestStatus.OPEN,
        nullable=False,
        index=True,
    )
    priority: Mapped[ServiceRequestPriority] = mapped_column(
        SAEnum(ServiceRequestPriority, name="service_request_priority", create_constraint=False),
        default=ServiceRequestPriority.MEDIUM,
        nullable=False,
        index=True,
    )
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    client = relationship("Client", lazy="selectin")
    assignee = relationship("Profile", foreign_keys=[assigned_to], lazy="selectin")
    messages = relationship(
        "ServiceRequestMessage", back_populates="request",
        lazy="selectin", order_by="ServiceRequestMessage.created_at"
    )

    def __repr__(self) -> str:
        return f"<ServiceRequest {self.ticket_number} status={self.status.value}>"


class ServiceRequestMessage(Base, TimestampMixin):
    """A message within a service request conversation."""

    __tablename__ = "service_request_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    author_type: Mapped[str] = mapped_column(
        String(20), nullable=False  # 'client' | 'admin'
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    request = relationship("ServiceRequest", back_populates="messages", lazy="selectin")
    author = relationship("Profile", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ServiceRequestMessage {self.id} type={self.author_type}>"
