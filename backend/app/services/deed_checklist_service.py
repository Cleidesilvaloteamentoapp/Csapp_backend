"""Escrituração checklist: created when a contract reaches its final cycle."""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client_lot import ClientLot
from app.models.deed_checklist import DeedChecklist, default_items


async def ensure_deed_checklist(
    db: AsyncSession, client_lot: ClientLot
) -> DeedChecklist:
    """Return the contract's checklist, creating it on first use.

    Idempotent: the final cycle can be reached by the scheduled trigger and by a
    manual approval, and both call this.
    """
    existing = (await db.execute(
        select(DeedChecklist).where(DeedChecklist.client_lot_id == client_lot.id)
    )).scalar_one_or_none()
    if existing:
        return existing

    checklist = DeedChecklist(
        company_id=client_lot.company_id,
        client_lot_id=client_lot.id,
        items=default_items(),
    )
    db.add(checklist)
    await db.flush()
    return checklist


async def uploaded_document_types(
    db: AsyncSession, client_lot: ClientLot
) -> list[str]:
    """Document types the client has already uploaded and had approved.

    Read from client_documents, the real document store -- the legacy
    clients.documents JSONB column is not maintained.
    """
    from app.models.client_document import ClientDocument
    from app.models.enums import DocumentStatus

    rows = await db.execute(
        select(ClientDocument.document_type).where(
            ClientDocument.client_id == client_lot.client_id,
            ClientDocument.status == DocumentStatus.APPROVED,
        )
    )
    return sorted(
        {r[0].value if hasattr(r[0], "value") else str(r[0]) for r in rows.all() if r[0]}
    )
