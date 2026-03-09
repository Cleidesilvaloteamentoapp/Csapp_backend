"""BatchOperation model — tracks batch boleto creation and bulk operations."""

import enum
import uuid
from typing import Optional

from sqlalchemy import Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin


class BatchOperationType(str, enum.Enum):
    BATCH_CREATE = "BATCH_CREATE"
    BATCH_BAIXA = "BATCH_BAIXA"
    BATCH_ALTERAR_VENCIMENTO = "BATCH_ALTERAR_VENCIMENTO"
    BATCH_ALTERAR_JUROS = "BATCH_ALTERAR_JUROS"
    BATCH_ALTERAR_DESCONTO = "BATCH_ALTERAR_DESCONTO"
    BATCH_CONCEDER_ABATIMENTO = "BATCH_CONCEDER_ABATIMENTO"
    BATCH_CANCELAR_ABATIMENTO = "BATCH_CANCELAR_ABATIMENTO"
    BATCH_NEGATIVACAO = "BATCH_NEGATIVACAO"
    BATCH_SUSTAR_NEGATIVACAO_BAIXAR = "BATCH_SUSTAR_NEGATIVACAO_BAIXAR"


class BatchOperationStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class BatchFrequency(str, enum.Enum):
    MENSAL = "MENSAL"
    TRIMESTRAL = "TRIMESTRAL"
    SEMESTRAL = "SEMESTRAL"
    ANUAL = "ANUAL"


class BatchOperation(Base, TenantMixin, TimestampMixin):
    """Tracks batch boleto creation and bulk operations with progress."""

    __tablename__ = "batch_operations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING", index=True
    )

    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True
    )
    frequency: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    duration_months: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    total_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    input_data: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    results: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    error_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )

    client = relationship("Client", lazy="selectin")
    creator = relationship("Profile", foreign_keys=[created_by], lazy="selectin")

    def __repr__(self) -> str:
        return f"<BatchOperation {self.id} type={self.type} status={self.status}>"
