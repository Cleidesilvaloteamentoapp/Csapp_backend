
"""Admin endpoints for contract history management."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_company_admin, require_permission
from app.models.enums import ContractEventType
from app.models.user import Profile
from app.schemas.contract_history import ContractHistoryCreate, ContractHistoryResponse
from app.services import contract_history_service
from app.services.client_service import get_client

router = APIRouter(prefix="/contract-history", tags=["Admin Contract History"])


@router.get("/client/{client_id}", response_model=list[ContractHistoryResponse])
async def list_client_history(
    client_id: UUID,
    client_lot_id: Optional[UUID] = Query(None),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_clients")),
):
    """List all contract history events for a client."""
    await get_client(db, admin.company_id, client_id)

    evt = None
    if event_type:
        try:
            evt = ContractEventType(event_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid event_type: {event_type}")

    entries = await contract_history_service.get_client_history(
        db, admin.company_id, client_id,
        client_lot_id=client_lot_id,
        event_type=evt,
        limit=limit,
        offset=offset,
    )
    return [ContractHistoryResponse.model_validate(e) for e in entries]


@router.post("/", response_model=ContractHistoryResponse, status_code=status.HTTP_201_CREATED)
async def add_history_entry(
    data: ContractHistoryCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_clients")),
):
    """Manually add a history note or manual write-off record."""
    await get_client(db, admin.company_id, data.client_id)

    try:
        evt = ContractEventType(data.event_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid event_type: {data.event_type}")

    entry = await contract_history_service.record_event(
        db,
        company_id=admin.company_id,
        client_id=data.client_id,
        client_lot_id=data.client_lot_id,
        event_type=evt,
        description=data.description,
        amount=data.amount,
        metadata_json=data.metadata_json,
        performed_by=admin.id,
        ip_address=request.client.host if request.client else None,
    )
    return ContractHistoryResponse.model_validate(entry)
