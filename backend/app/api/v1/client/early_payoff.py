
"""Client endpoint for requesting early payoff / payment anticipation."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_client_user
from app.models.client import Client
from app.models.client_lot import ClientLot
from app.models.early_payoff_request import EarlyPayoffRequest
from app.models.enums import ClientLotStatus, EarlyPayoffStatus
from app.models.user import Profile
from app.schemas.early_payoff import EarlyPayoffCreate, EarlyPayoffResponse
from app.services.notification_service import create_notification
from app.models.enums import NotificationType
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/early-payoff", tags=["Client Early Payoff"])


async def _get_client_for_user(db: AsyncSession, user: Profile) -> Client:
    row = await db.execute(
        select(Client).where(Client.profile_id == user.id, Client.company_id == user.company_id)
    )
    client = row.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client profile not found")
    return client


@router.post("", response_model=EarlyPayoffResponse, status_code=status.HTTP_201_CREATED)
async def request_early_payoff(
    payload: EarlyPayoffCreate,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Client requests early payoff for one of their lots. Admin is notified."""
    client = await _get_client_for_user(db, user)

    # Verify the client_lot belongs to this client and is active
    cl_row = await db.execute(
        select(ClientLot).where(
            ClientLot.id == payload.client_lot_id,
            ClientLot.client_id == client.id,
            ClientLot.company_id == user.company_id,
            ClientLot.status == ClientLotStatus.ACTIVE,
        )
    )
    client_lot = cl_row.scalar_one_or_none()
    if not client_lot:
        raise HTTPException(status_code=404, detail="Active lot not found for this client")

    # Check for existing pending request
    existing = await db.execute(
        select(EarlyPayoffRequest).where(
            EarlyPayoffRequest.client_id == client.id,
            EarlyPayoffRequest.client_lot_id == payload.client_lot_id,
            EarlyPayoffRequest.status == EarlyPayoffStatus.PENDING,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="You already have a pending early payoff request for this lot")

    req = EarlyPayoffRequest(
        company_id=user.company_id,
        client_id=client.id,
        client_lot_id=payload.client_lot_id,
        status=EarlyPayoffStatus.PENDING,
        client_message=payload.client_message,
    )
    db.add(req)
    await db.flush()

    # Notify admins
    try:
        await create_notification(
            db,
            company_id=user.company_id,
            notification_type=NotificationType.ANTECIPACAO_SOLICITADA,
            title="Solicitação de Antecipação",
            message=f"Cliente {client.full_name} solicitou antecipação de pagamento.",
            data={"request_id": str(req.id), "client_id": str(client.id)},
        )
    except Exception as exc:
        logger.warning("early_payoff_notification_failed", error=str(exc))

    await db.commit()
    await db.refresh(req)
    logger.info("early_payoff_requested", request_id=str(req.id), client_id=str(client.id))
    return EarlyPayoffResponse.model_validate(req)


@router.get("", response_model=list[EarlyPayoffResponse])
async def list_my_requests(
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """List the client's own early payoff requests."""
    client = await _get_client_for_user(db, user)

    rows = await db.execute(
        select(EarlyPayoffRequest)
        .where(
            EarlyPayoffRequest.client_id == client.id,
            EarlyPayoffRequest.company_id == user.company_id,
        )
        .order_by(EarlyPayoffRequest.requested_at.desc())
    )
    return [EarlyPayoffResponse.model_validate(r) for r in rows.scalars().all()]
