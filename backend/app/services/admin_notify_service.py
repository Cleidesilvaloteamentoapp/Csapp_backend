
"""Central helper for sending admin notifications (in-app + WhatsApp).

All calls are best-effort: failures are logged but never raise to callers.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company_notification_settings import CompanyNotificationSettings
from app.models.enums import NotificationType, UserRole
from app.models.user import Profile
from app.services.notification_service import create_notification
from app.services.notification_settings_service import get_or_create, is_enabled
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def notify_admins(
    db: AsyncSession,
    company_id: UUID,
    settings_key: str,
    *,
    title: str,
    message: str,
    n_type: NotificationType,
    data: Optional[dict] = None,
    staff_permission: Optional[str] = None,
) -> None:
    """Create in-app notifications for all company admins and send WhatsApp to configured numbers.

    Args:
        settings_key: field name in CompanyNotificationSettings to gate the send.
        title/message/n_type/data: notification content.
        staff_permission: when set, STAFF holding this flag are notified too.
            Staff who can act on something should hear about it -- a cycle
            approval is actionable by anyone with `manage_financial`.
    """
    try:
        settings = await get_or_create(db, company_id)
        if not is_enabled(settings, settings_key):
            return

        # In-app notifications for every admin of the company. Filtering on
        # COMPANY_ADMIN alone reached nobody: nothing in the system creates that
        # role -- signup and /admin/superadmins both create SUPER_ADMIN -- so the
        # cycle-renewal alert never had a recipient.
        admin_profiles = (
            await db.execute(
                select(Profile).where(
                    Profile.company_id == company_id,
                    Profile.role.in_([UserRole.SUPER_ADMIN, UserRole.COMPANY_ADMIN]),
                    Profile.is_active.is_(True),
                )
            )
        ).scalars().all()

        recipients = list(admin_profiles)

        if staff_permission:
            from app.models.staff_permission import StaffPermission

            staff_rows = (
                await db.execute(
                    select(Profile)
                    .join(StaffPermission, StaffPermission.profile_id == Profile.id)
                    .where(
                        Profile.company_id == company_id,
                        Profile.role == UserRole.STAFF,
                        Profile.is_active.is_(True),
                        getattr(StaffPermission, staff_permission).is_(True),
                    )
                )
            ).scalars().all()
            recipients.extend(staff_rows)

        for profile in recipients:
            try:
                await create_notification(
                    db,
                    company_id=company_id,
                    user_id=profile.id,
                    title=title,
                    message=message,
                    notification_type=n_type,
                    data=data or {},
                )
            except Exception as exc:
                logger.warning(
                    "admin_in_app_notify_failed",
                    profile_id=str(profile.id),
                    error=str(exc),
                )

        # WhatsApp for configured admin numbers
        admin_numbers = settings.get_admin_numbers()
        if admin_numbers:
            from app.services.whatsapp_service import send_whatsapp_message

            for number in admin_numbers:
                try:
                    await send_whatsapp_message(
                        to=number,
                        body=f"[Admin] {title}\n{message}",
                        db=db,
                        company_id=company_id,
                    )
                except Exception as exc:
                    logger.warning(
                        "admin_whatsapp_notify_failed",
                        number=number,
                        error=str(exc),
                    )

    except Exception as exc:
        logger.error(
            "notify_admins_failed",
            company_id=str(company_id),
            key=settings_key,
            error=str(exc),
        )
