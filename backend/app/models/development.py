from decimal import Decimal
from typing import Optional

"""Development model – real-estate developments (loteamentos)."""

import uuid

from sqlalchemy import Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin
from app.models.enums import PropertyType


class Development(Base, TenantMixin, TimestampMixin):
    """A loteamento (housing development) owned by a company."""

    __tablename__ = "developments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    documents: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    # Property type (required)
    property_type: Mapped[PropertyType] = mapped_column(
        String(20), nullable=False, default=PropertyType.LOT
    )

    # Lot-specific fields
    block: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    lot_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    area_m2: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)

    # Residential-specific fields (House/Apartment)
    bedrooms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bathrooms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    suites: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    parking_spaces: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    construction_area_m2: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    total_area_m2: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True
    )

    # General fields
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)

    # Relationships
    lots = relationship("Lot", back_populates="development", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Development {self.name} ({self.property_type.value})>"
