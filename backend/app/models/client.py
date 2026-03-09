from typing import Optional

"""Client model – end-customers of each company."""

import uuid

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin
from app.models.enums import ClientStatus


class Client(Base, TenantMixin, TimestampMixin):
    """A client belonging to a specific company (tenant)."""

    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    cpf_cnpj: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    contract_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, unique=True, index=True)
    matricula: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    address: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    documents: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[ClientStatus] = mapped_column(
        SAEnum(ClientStatus, name="client_status", create_constraint=False),
        default=ClientStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    asaas_customer_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    profile = relationship("Profile", foreign_keys=[profile_id], lazy="selectin")
    creator = relationship("Profile", foreign_keys=[created_by], lazy="selectin")
    client_lots = relationship("ClientLot", back_populates="client", lazy="selectin")
    boletos = relationship("Boleto", back_populates="client", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Client {self.full_name}>"
