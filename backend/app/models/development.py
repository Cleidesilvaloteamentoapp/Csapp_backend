"""Development model – real-estate developments (loteamentos)."""

import uuid

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin


class Development(Base, TenantMixin, TimestampMixin):
    """A loteamento (housing development) owned by a company."""

    __tablename__ = "developments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    documents: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    # Relationships
    lots = relationship("Lot", back_populates="development", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Development {self.name}>"
