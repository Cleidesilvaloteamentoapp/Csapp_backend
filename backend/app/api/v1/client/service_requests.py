from typing import Optional

"""Client service request (ticket) endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_client_user
from app.models.client import Client
from app.models.enums import ServiceRequestStatus, ServiceRequestType, ServiceRequestPriority
from app.models.service_request import ServiceRequest, ServiceRequestMessage
from app.models.user import Profile
from app.schemas.service_request import (
    ServiceRequestCreate,
    ServiceRequestDetailResponse,
    ServiceRequestListResponse,
    ServiceRequestMessageCreate,
    ServiceRequestMessageResponse,
    ServiceRequestResponse,
)

router = APIRouter(prefix="/service-requests", tags=["Client Service Requests"])


async def _get_client(db: AsyncSession, user: Profile) -> Client:
    row = await db.execute(
        select(Client).where(Client.profile_id == user.id, Client.company_id == user.company_id)
    )
    client = row.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client profile not found")
    return client


async def _generate_ticket_number(db: AsyncSession, company_id) -> str:
    """Generate a unique ticket number: REQ-YYYY-NNNN."""
    from datetime import datetime, timezone

    year = datetime.now(timezone.utc).year
    row = await db.execute(
        select(func.count(ServiceRequest.id)).where(
            ServiceRequest.company_id == company_id,
            ServiceRequest.ticket_number.like(f"REQ-{year}-%"),
        )
    )
    count = row.scalar() or 0
    return f"REQ-{year}-{str(count + 1).zfill(4)}"


def _to_response(sr: ServiceRequest) -> dict:
    """Convert ServiceRequest to response dict with assignee_name."""
    data = ServiceRequestResponse.model_validate(sr).model_dump()
    if sr.assignee:
        data["assignee_name"] = sr.assignee.full_name
    return data


def _msg_to_response(msg: ServiceRequestMessage) -> dict:
    """Convert message to response with author_name."""
    data = ServiceRequestMessageResponse.model_validate(msg).model_dump()
    if msg.author:
        data["author_name"] = msg.author.full_name
    return data


@router.post("", response_model=ServiceRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_service_request(
    body: ServiceRequestCreate,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Create a new service request (support ticket)."""
    client = await _get_client(db, user)

    ticket_number = await _generate_ticket_number(db, user.company_id)

    sr = ServiceRequest(
        company_id=user.company_id,
        client_id=client.id,
        ticket_number=ticket_number,
        service_type=ServiceRequestType(body.service_type),
        subject=body.subject,
        description=body.description,
        priority=ServiceRequestPriority(body.priority),
        status=ServiceRequestStatus.OPEN,
    )
    db.add(sr)
    await db.flush()

    # Create the initial message from the description
    msg = ServiceRequestMessage(
        request_id=sr.id,
        author_id=user.id,
        author_type="client",
        message=body.description,
        is_internal=False,
    )
    db.add(msg)
    await db.flush()

    return _to_response(sr)


@router.get("", response_model=ServiceRequestListResponse)
async def list_service_requests(
    req_status: Optional[str] = Query(None, alias="status", pattern=r"^(OPEN|IN_PROGRESS|WAITING_CLIENT|RESOLVED|CLOSED)$"),
    service_type: Optional[str] = Query(None, pattern=r"^(MANUTENCAO|SUPORTE|FINANCEIRO|DOCUMENTACAO|OUTROS)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """List service requests for the authenticated client."""
    client = await _get_client(db, user)

    base = select(ServiceRequest).where(
        ServiceRequest.client_id == client.id,
        ServiceRequest.company_id == user.company_id,
    )
    if req_status:
        base = base.where(ServiceRequest.status == req_status)
    if service_type:
        base = base.where(ServiceRequest.service_type == service_type)

    # Count total
    count_row = await db.execute(
        select(func.count()).select_from(base.subquery())
    )
    total = count_row.scalar() or 0

    # Paginate
    offset = (page - 1) * per_page
    rows = await db.execute(
        base.order_by(ServiceRequest.created_at.desc()).offset(offset).limit(per_page)
    )
    items = [_to_response(sr) for sr in rows.scalars().all()]

    return ServiceRequestListResponse(items=items, total=total, page=page, per_page=per_page)


@router.get("/{request_id}", response_model=ServiceRequestDetailResponse)
async def get_service_request(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Get service request details with messages (excludes internal messages)."""
    client = await _get_client(db, user)

    row = await db.execute(
        select(ServiceRequest).where(
            ServiceRequest.id == request_id,
            ServiceRequest.client_id == client.id,
            ServiceRequest.company_id == user.company_id,
        )
    )
    sr = row.scalar_one_or_none()
    if not sr:
        raise HTTPException(status_code=404, detail="Service request not found")

    # Get non-internal messages
    msg_rows = await db.execute(
        select(ServiceRequestMessage)
        .where(
            ServiceRequestMessage.request_id == sr.id,
            ServiceRequestMessage.is_internal.is_(False),
        )
        .order_by(ServiceRequestMessage.created_at.asc())
    )
    messages = [_msg_to_response(m) for m in msg_rows.scalars().all()]

    data = _to_response(sr)
    data["messages"] = messages
    return data


@router.post("/{request_id}/messages", response_model=ServiceRequestMessageResponse, status_code=status.HTTP_201_CREATED)
async def add_message(
    request_id: UUID,
    body: ServiceRequestMessageCreate,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Add a message to an existing service request."""
    client = await _get_client(db, user)

    row = await db.execute(
        select(ServiceRequest).where(
            ServiceRequest.id == request_id,
            ServiceRequest.client_id == client.id,
            ServiceRequest.company_id == user.company_id,
        )
    )
    sr = row.scalar_one_or_none()
    if not sr:
        raise HTTPException(status_code=404, detail="Service request not found")

    if sr.status in (ServiceRequestStatus.CLOSED, ServiceRequestStatus.RESOLVED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot add messages to a closed or resolved request",
        )

    msg = ServiceRequestMessage(
        request_id=sr.id,
        author_id=user.id,
        author_type="client",
        message=body.message,
        is_internal=False,
    )
    db.add(msg)

    # If waiting on client, move back to IN_PROGRESS
    if sr.status == ServiceRequestStatus.WAITING_CLIENT:
        sr.status = ServiceRequestStatus.IN_PROGRESS

    await db.flush()

    return _msg_to_response(msg)
