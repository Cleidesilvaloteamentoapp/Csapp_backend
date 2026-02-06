from typing import Optional

"""Referral model – client referral programme."""

import uuid

from sqlalchemy import Enum as SAEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin
from app.models.enums import ReferralStatus


class Referral(Base, TenantMixin, TimestampMixin):
    """A referral made by an existing client."""

    __tablename__ = "referrals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    referrer_client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    referred_name: Mapped[str] = mapped_column(String(255), nullable=False)
    referred_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    referred_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[ReferralStatus] = mapped_column(
        SAEnum(ReferralStatus, name="referral_status", create_constraint=True),
        default=ReferralStatus.PENDING,
        nullable=False,
        index=True,
    )

    # Relationships
    referrer = relationship("Client", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Referral from={self.referrer_client_id} name={self.referred_name}>"
