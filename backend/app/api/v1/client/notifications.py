from typing import Optional

"""Client notification endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_client_user
from app.models.notification import Notification
from app.models.user import Profile
from app.schemas.notification import NotificationResponse, UnreadCountResponse

router = APIRouter(prefix="/notifications", tags=["Client Notifications"])


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    is_read: Optional[bool] = None,
    notification_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """List notifications for the authenticated user."""
    query = select(Notification).where(
        Notification.user_id == user.id,
        Notification.company_id == user.company_id,
    )
    if is_read is not None:
        query = query.where(Notification.is_read == is_read)
    if notification_type:
        query = query.where(Notification.type == notification_type)

    offset = (page - 1) * per_page
    query = query.order_by(Notification.created_at.desc()).offset(offset).limit(per_page)

    rows = await db.execute(query)
    return [NotificationResponse.model_validate(n) for n in rows.scalars().all()]


@router.get("/unread-count", response_model=UnreadCountResponse)
async def unread_count(
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Get count of unread notifications."""
    row = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user.id,
            Notification.company_id == user.company_id,
            Notification.is_read.is_(False),
        )
    )
    return UnreadCountResponse(unread_count=row.scalar() or 0)


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_as_read(
    notification_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Mark a single notification as read."""
    row = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
            Notification.company_id == user.company_id,
        )
    )
    notif = row.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")

    notif.is_read = True
    await db.flush()
    return NotificationResponse.model_validate(notif)


@router.patch("/read-all", status_code=status.HTTP_200_OK)
async def mark_all_as_read(
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Mark all notifications as read."""
    await db.execute(
        update(Notification)
        .where(
            Notification.user_id == user.id,
            Notification.company_id == user.company_id,
            Notification.is_read.is_(False),
        )
        .values(is_read=True)
    )
    await db.flush()
    return {"detail": "All notifications marked as read"}
