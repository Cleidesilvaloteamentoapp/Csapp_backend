from typing import Optional
from datetime import date
from decimal import Decimal
import uuid

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Date, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin
from app.models.enums import BoletoStatus, BoletoTag, WriteoffType


class Boleto(Base, TenantMixin, TimestampMixin):
    """Boleto Sicredi record linked to a client."""

    __tablename__ = "boletos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    nosso_numero: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    seu_numero: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    linha_digitavel: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    codigo_barras: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    tipo_cobranca: Mapped[str] = mapped_column(String(20), nullable=False)
    especie_documento: Mapped[str] = mapped_column(String(50), nullable=False)
    
    tag: Mapped[Optional[BoletoTag]] = mapped_column(
        SAEnum(BoletoTag, name="boleto_tag", create_constraint=False),
        nullable=True,
        index=True,
    )
    installment_label: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    data_vencimento: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    data_emissao: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    data_liquidacao: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    valor_liquidacao: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    
    status: Mapped[BoletoStatus] = mapped_column(
        SAEnum(BoletoStatus, name="boleto_status", create_constraint=False),
        default=BoletoStatus.NORMAL,
        nullable=False,
        index=True,
    )
    
    txid: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    qr_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True
    )
    
    pagador_data: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    raw_response: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    
    writeoff_type: Mapped[Optional[WriteoffType]] = mapped_column(
        SAEnum(WriteoffType, name="writeoff_type", create_constraint=False),
        nullable=True,
    )
    writeoff_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    writeoff_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )

    client = relationship("Client", back_populates="boletos", lazy="selectin")
    invoice = relationship("Invoice", back_populates="boletos", lazy="selectin")
    creator = relationship("Profile", foreign_keys=[created_by], lazy="selectin")

    def __repr__(self) -> str:
        return f"<Boleto {self.nosso_numero} - {self.client_id}>"
