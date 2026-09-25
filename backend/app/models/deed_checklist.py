"""DeedChecklist model – escrituração checklist raised on a contract's final cycle.

When the last 12-installment cycle is released, the contract is heading for
deed transfer (escrituração). The checklist gives the admin the concrete list of
documents that has to be gathered, resolved against the documents the client has
already uploaded rather than tracked as a second, divergent copy.
"""

from typing import Optional

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin
from app.models.enums import DocumentType

# Documents a deed transfer needs, in the order an admin collects them. These are
# existing DocumentType values, so an upload the client already made satisfies
# the item instead of requiring a second copy.
DEED_DOCUMENT_TYPES: tuple[tuple[DocumentType, str], ...] = (
    (DocumentType.MATRICULA, "Matrícula do imóvel"),
    (DocumentType.CONTRATO, "Contrato de compra e venda"),
    (DocumentType.IPTU, "IPTU / certidão de valor venal"),
    (DocumentType.CERTIDAO_ESTADO_CIVIL, "Certidão de estado civil"),
    (DocumentType.GUIA_INFORMACAO, "Guia de informação (ITBI)"),
    (DocumentType.RG, "Documento de identidade"),
    (DocumentType.CPF, "CPF"),
    (DocumentType.COMPROVANTE_RESIDENCIA, "Comprovante de residência"),
)


def default_items() -> list[dict]:
    """The starting checklist: every deed document, none done yet."""
    return [
        {
            "document_type": doc_type.value,
            "label": label,
            "done": False,
            "note": None,
            "updated_at": None,
        }
        for doc_type, label in DEED_DOCUMENT_TYPES
    ]


class DeedChecklist(Base, TenantMixin, TimestampMixin):
    """Escrituração checklist for a contract reaching its final cycle."""

    __tablename__ = "deed_checklists"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_lot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client_lots.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    items: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=default_items, server_default=text("'[]'::jsonb"),
        comment="[{document_type, label, done, note, updated_at}]",
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    client_lot = relationship("ClientLot", lazy="selectin")

    @property
    def is_complete(self) -> bool:
        return bool(self.items) and all(item.get("done") for item in self.items)

    def mark_completion(self) -> None:
        """Keep `completed_at` in step with the items, both ways."""
        if self.is_complete and self.completed_at is None:
            self.completed_at = datetime.now(timezone.utc)
        elif not self.is_complete:
            self.completed_at = None

    def __repr__(self) -> str:
        done = sum(1 for i in (self.items or []) if i.get("done"))
        return f"<DeedChecklist lot={self.client_lot_id} {done}/{len(self.items or [])}>"
