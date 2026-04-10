"""Profile model – extends Supabase auth.users with app-specific data."""

import uuid
from typing import Optional

from sqlalchemy import Boolean, Enum as SAEnum
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin
from app.models.enums import UserRole


class Profile(Base, TenantMixin, TimestampMixin):
    """User profile linked to Supabase auth.users via id."""

    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", create_constraint=False),
        nullable=False,
        index=True,
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    cpf_cnpj: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    # Relationships
    company = relationship("Company", back_populates="profiles", lazy="selectin")
    staff_permission = relationship(
        "StaffPermission", back_populates="profile", uselist=False, lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Profile {self.full_name} role={self.role.value}>"
