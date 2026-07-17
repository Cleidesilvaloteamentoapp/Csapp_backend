
"""Admin endpoint for auditing the Sicredi interaction log."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select
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
    webhook_event_id: Optional[str] = None
    http_status: Optional[int] = None
    success: Optional[bool] = None
    payload: Optional[dict] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SicrediEventListResponse(BaseModel):
    """Paginated envelope for the audit listing."""

    items: list[SicrediEventResponse]
    total: int


@router.get("", response_model=SicrediEventListResponse)
async def list_sicredi_events(
    direction: Optional[str] = Query(None, description="INBOUND or OUTBOUND"),
    nosso_numero: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_financial")),
):
    """List Sicredi audit events for the admin's company (newest first).

    Also includes events with a NULL company_id: those are inbound webhooks (or
    outbound calls) the system could not tie to a company — e.g. a payment for a
    nossoNumero we don't have locally. Hiding them is exactly how a missed
    payment stays invisible, so admins with manage_financial see them flagged as
    "empresa não identificada" in the UI.
    """
    company_filter = or_(
        SicrediEvent.company_id == admin.company_id,
        SicrediEvent.company_id.is_(None),
    )
    filters = [company_filter]
    if direction:
        filters.append(SicrediEvent.direction == direction.upper())
    if nosso_numero:
        filters.append(SicrediEvent.nosso_numero == nosso_numero)
    if event_type:
        filters.append(SicrediEvent.event_type == event_type)

    total = (
        await db.execute(select(func.count()).select_from(SicrediEvent).where(*filters))
    ).scalar_one()

    stmt = (
        select(SicrediEvent)
        .where(*filters)
        .order_by(SicrediEvent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    items = [SicrediEventResponse.model_validate(e) for e in result.scalars().all()]
    return SicrediEventListResponse(items=items, total=total)
