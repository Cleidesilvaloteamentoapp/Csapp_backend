"""Client referral endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_client_user
from app.models.client import Client
from app.models.referral import Referral
from app.models.user import Profile
from app.schemas.referral import ReferralCreate, ReferralResponse

router = APIRouter(prefix="/referrals", tags=["Client Referrals"])


async def _get_client(db: AsyncSession, user: Profile) -> Client | None:
    row = await db.execute(
        select(Client).where(Client.profile_id == user.id, Client.company_id == user.company_id)
    )
    return row.scalar_one_or_none()


@router.post("/", response_model=ReferralResponse, status_code=status.HTTP_201_CREATED)
async def create_referral(
    data: ReferralCreate,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Submit a referral."""
    client = await _get_client(db, user)
    if not client:
        raise HTTPException(status_code=404, detail="Client profile not found")

    referral = Referral(
        company_id=user.company_id,
        referrer_client_id=client.id,
        referred_name=data.referred_name,
        referred_phone=data.referred_phone,
        referred_email=data.referred_email,
    )
    db.add(referral)
    await db.flush()
    return ReferralResponse.model_validate(referral)


@router.get("/", response_model=list[ReferralResponse])
async def list_referrals(
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """List referrals made by the current client."""
    client = await _get_client(db, user)
    if not client:
        return []

    rows = await db.execute(
        select(Referral)
        .where(Referral.referrer_client_id == client.id, Referral.company_id == user.company_id)
        .order_by(Referral.created_at.desc())
    )
    return [ReferralResponse.model_validate(r) for r in rows.scalars().all()]
