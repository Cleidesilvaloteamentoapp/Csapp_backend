
"""Admin endpoint for auditing the Sicredi interaction log."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_permission
from app.models.sicredi_event import SicrediEvent
from app.models.user import Profile

router = APIRouter(prefix="/sicredi-events", tags=["Admin Sicredi Audit"])


class SicrediEventResponse(BaseModel):
    """One audited Sicredi request or response."""

    id: UUID
    company_id: Optional[UUID] = None
    direction: str
    event_type: str
    nosso_numero: Optional[str] = None
    boleto_id: Optional[UUID] = None
    invoice_id: Optional[UUID] = None
    http_status: Optional[int] = None
    success: Optional[bool] = None
    payload: Optional[dict] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


@router.get("", response_model=list[SicrediEventResponse])
async def list_sicredi_events(
    direction: Optional[str] = Query(None, description="INBOUND or OUTBOUND"),
    nosso_numero: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_financial")),
):
    """List Sicredi audit events for the admin's company (newest first)."""
    stmt = select(SicrediEvent).where(SicrediEvent.company_id == admin.company_id)
    if direction:
        stmt = stmt.where(SicrediEvent.direction == direction.upper())
    if nosso_numero:
        stmt = stmt.where(SicrediEvent.nosso_numero == nosso_numero)
    if event_type:
        stmt = stmt.where(SicrediEvent.event_type == event_type)

    stmt = stmt.order_by(SicrediEvent.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return [SicrediEventResponse.model_validate(e) for e in result.scalars().all()]
