from typing import Optional

"""Admin service request (ticket) management endpoints."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.database import get_db
from app.core.deps import get_company_admin
from app.models.enums import ServiceRequestStatus
from app.models.service_request import ServiceRequest, ServiceRequestMessage
from app.models.user import Profile
from app.schemas.service_request import (
    ServiceRequestAdminUpdate,
    ServiceRequestDetailResponse,
    ServiceRequestListResponse,
    ServiceRequestMessageCreate,
    ServiceRequestMessageResponse,
    ServiceRequestResponse,
)

router = APIRouter(prefix="/service-requests", tags=["Admin Service Requests"])


def _to_response(sr: ServiceRequest) -> dict:
    from app.schemas.service_request import ServiceRequestResponse as SR
    data = SR.model_validate(sr).model_dump()
    if sr.assignee:
        data["assignee_name"] = sr.assignee.full_name
    return data


def _msg_to_response(msg: ServiceRequestMessage) -> dict:
    data = ServiceRequestMessageResponse.model_validate(msg).model_dump()
    if msg.author:
        data["author_name"] = msg.author.full_name
    return data


@router.get("/", response_model=ServiceRequestListResponse)
async def list_all_requests(
    client_id: Optional[UUID] = None,
    req_status: Optional[str] = Query(None, alias="status", pattern=r"^(OPEN|IN_PROGRESS|WAITING_CLIENT|RESOLVED|CLOSED)$"),
    service_type: Optional[str] = Query(None, pattern=r"^(MANUTENCAO|SUPORTE|FINANCEIRO|DOCUMENTACAO|OUTROS)$"),
    priority: Optional[str] = Query(None, pattern=r"^(LOW|MEDIUM|HIGH|URGENT)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_company_admin),
):
    """List all service requests for the company."""
    base = select(ServiceRequest).where(ServiceRequest.company_id == user.company_id)

    if client_id:
        base = base.where(ServiceRequest.client_id == client_id)
    if req_status:
        base = base.where(ServiceRequest.status == req_status)
    if service_type:
        base = base.where(ServiceRequest.service_type == service_type)
    if priority:
        base = base.where(ServiceRequest.priority == priority)

    count_row = await db.execute(select(func.count()).select_from(base.subquery()))
    total = count_row.scalar() or 0

    offset = (page - 1) * per_page
    rows = await db.execute(
        base.order_by(ServiceRequest.created_at.desc()).offset(offset).limit(per_page)
    )
    items = [_to_response(sr) for sr in rows.scalars().all()]

    return ServiceRequestListResponse(items=items, total=total, page=page, per_page=per_page)


@router.get("/stats")
async def request_stats(
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_company_admin),
):
    """Get counts by status for the company."""
    rows = await db.execute(
        select(ServiceRequest.status, func.count(ServiceRequest.id))
        .where(ServiceRequest.company_id == user.company_id)
        .group_by(ServiceRequest.status)
    )
    stats = {r[0].value if hasattr(r[0], "value") else r[0]: r[1] for r in rows.all()}
    return stats


@router.get("/{request_id}", response_model=ServiceRequestDetailResponse)
async def get_request_detail(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_company_admin),
):
    """Get service request details with ALL messages (including internal)."""
    row = await db.execute(
        select(ServiceRequest).where(
            ServiceRequest.id == request_id,
            ServiceRequest.company_id == user.company_id,
        )
    )
    sr = row.scalar_one_or_none()
    if not sr:
        raise HTTPException(status_code=404, detail="Service request not found")

    msg_rows = await db.execute(
        select(ServiceRequestMessage)
        .where(ServiceRequestMessage.request_id == sr.id)
        .order_by(ServiceRequestMessage.created_at.asc())
    )
    messages = [_msg_to_response(m) for m in msg_rows.scalars().all()]

    data = _to_response(sr)
    data["messages"] = messages
    return data


@router.patch("/{request_id}", response_model=ServiceRequestResponse)
async def update_request(
    request_id: UUID,
    body: ServiceRequestAdminUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_company_admin),
):
    """Update service request status, priority, or assignment."""
    row = await db.execute(
        select(ServiceRequest).where(
            ServiceRequest.id == request_id,
            ServiceRequest.company_id == user.company_id,
        )
    )
    sr = row.scalar_one_or_none()
    if not sr:
        raise HTTPException(status_code=404, detail="Service request not found")

    changes = {}
    if body.status is not None:
        old = sr.status.value if hasattr(sr.status, "value") else sr.status
        sr.status = ServiceRequestStatus(body.status)
        changes["status"] = {"old": old, "new": body.status}
        if body.status == "RESOLVED":
            sr.resolved_at = datetime.now(timezone.utc)
    if body.priority is not None:
        old = sr.priority.value if hasattr(sr.priority, "value") else sr.priority
        from app.models.enums import ServiceRequestPriority
        sr.priority = ServiceRequestPriority(body.priority)
        changes["priority"] = {"old": old, "new": body.priority}
    if body.assigned_to is not None:
        sr.assigned_to = body.assigned_to
        changes["assigned_to"] = str(body.assigned_to)

    if changes:
        await db.flush()
        await log_audit(
            db,
            user_id=user.id,
            company_id=user.company_id,
            table_name="service_requests",
            operation="SERVICE_REQUEST_UPDATE",
            resource_id=str(sr.id),
            detail=str(changes),
            ip_address=request.client.host if request.client else None,
        )

    return _to_response(sr)


@router.post("/{request_id}/messages", response_model=ServiceRequestMessageResponse, status_code=status.HTTP_201_CREATED)
async def admin_add_message(
    request_id: UUID,
    body: ServiceRequestMessageCreate,
    is_internal: bool = Query(False, description="Mark message as internal (not visible to client)"),
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_company_admin),
):
    """Add an admin message to a service request."""
    row = await db.execute(
        select(ServiceRequest).where(
            ServiceRequest.id == request_id,
            ServiceRequest.company_id == user.company_id,
        )
    )
    sr = row.scalar_one_or_none()
    if not sr:
        raise HTTPException(status_code=404, detail="Service request not found")

    msg = ServiceRequestMessage(
        request_id=sr.id,
        author_id=user.id,
        author_type="admin",
        message=body.message,
        is_internal=is_internal,
    )
    db.add(msg)
    await db.flush()

    return _msg_to_response(msg)
