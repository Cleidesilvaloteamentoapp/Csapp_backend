from typing import Optional

"""Company model – top-level tenant entity."""

import uuid

from sqlalchemy import Enum as SAEnum
from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin
from app.models.enums import CompanyStatus


class Company(Base, TimestampMixin):
    """Represents an imobiliária (real-estate company) using the platform."""

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    settings: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    status: Mapped[CompanyStatus] = mapped_column(
        SAEnum(CompanyStatus, name="company_status", create_constraint=False),
        default=CompanyStatus.ACTIVE,
        nullable=False,
        index=True,
    )

    # Relationships
    profiles = relationship("Profile", back_populates="company", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Company {self.name} ({self.slug})>"
