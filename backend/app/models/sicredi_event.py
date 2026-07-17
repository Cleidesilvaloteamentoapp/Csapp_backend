
"""SicrediEvent model – immutable audit log of every Sicredi interaction.

Stores BOTH directions of communication with the bank:
  * OUTBOUND: requests we send (boleto creation, cancellation, etc.)
  * INBOUND: webhooks/responses we receive (liquidação, etc.)

Kept forever so the admin can audit "our side" against "the bank's answers".
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class SicrediEvent(Base, TimestampMixin):
    """An immutable record of one Sicredi request or response."""

    __tablename__ = "sicredi_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Nullable: an inbound webhook may arrive before we can match a company.
    company_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # INBOUND | OUTBOUND
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)

    nosso_numero: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    boleto_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("boletos.id", ondelete="SET NULL"), nullable=True
    )
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True
    )

    # Sicredi's idempotency key for inbound webhooks (idEventoWebhook). Indexed,
    # NOT unique: redeliveries must still be insertable as WEBHOOK_DUPLICATE rows.
    webhook_event_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    success: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    # Full request or response payload, stored verbatim for audit.
    payload: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    def __repr__(self) -> str:
        return f"<SicrediEvent {self.direction} {self.event_type} {self.nosso_numero}>"
