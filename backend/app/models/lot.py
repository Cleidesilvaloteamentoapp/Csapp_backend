from typing import Optional

"""Lot model – individual lots within developments."""

import uuid
from decimal import Decimal

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin
from app.models.enums import LotStatus


class Lot(Base, TenantMixin, TimestampMixin):
    """An individual lot in a development."""

    __tablename__ = "lots"

    # A matrícula (registro de cartório) é única por empresa: impede o cadastro
    # duplicado do mesmo terreno. Índice parcial para não conflitar com lotes
    # legados que ainda não têm matrícula preenchida (registration_number NULL).
    __table_args__ = (
        Index(
            "uq_lots_company_registration",
            "company_id",
            "registration_number",
            unique=True,
            postgresql_where=text("registration_number IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    development_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("developments.id", ondelete="CASCADE"), nullable=False
    )
    lot_number: Mapped[str] = mapped_column(String(50), nullable=False)
    block: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Balneário / localidade do terreno (obrigatório na API para lotes novos).
    balneario: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    # Número de matrícula do imóvel (registro de cartório). Ver índice único acima.
    registration_number: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    area_m2: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[LotStatus] = mapped_column(
        SAEnum(LotStatus, name="lot_status", create_constraint=False),
        default=LotStatus.AVAILABLE,
        nullable=False,
        index=True,
    )
    documents: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    # Photo gallery: list of {id, path, is_primary, visible_to_client, caption}
    photos: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]", nullable=False)

    # Relationships
    development = relationship("Development", back_populates="lots", lazy="selectin")
    client_lots = relationship("ClientLot", back_populates="lot", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Lot {self.lot_number} block={self.block}>"
