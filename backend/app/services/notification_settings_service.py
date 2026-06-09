
"""Service for managing per-company WhatsApp/notification preferences."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company_notification_settings import CompanyNotificationSettings
from app.utils.logging import get_logger

logger = get_logger(__name__)

_UPDATABLE_FIELDS = {
    "notify_client_new_boleto",
    "notify_client_due_reminder",
    "notify_client_overdue",
    "notify_client_service",
    "notify_admin_client_created",
    "notify_admin_client_deleted",
    "notify_admin_boleto_generated",
    "notify_admin_boleto_cancelled",
    "notify_admin_cycle_request",
    "admin_whatsapp_numbers",
}


async def get_or_create(
    db: AsyncSession, company_id: UUID
) -> CompanyNotificationSettings:
    result = await db.execute(
        select(CompanyNotificationSettings).where(
            CompanyNotificationSettings.company_id == company_id
        )
    )
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = CompanyNotificationSettings(company_id=company_id)
        db.add(settings)
        await db.flush()
        logger.info("notification_settings_created", company_id=str(company_id))
    return settings


async def update(
    db: AsyncSession, company_id: UUID, **fields
) -> CompanyNotificationSettings:
    settings = await get_or_create(db, company_id)
    for key, value in fields.items():
        if key in _UPDATABLE_FIELDS and value is not None:
            setattr(settings, key, value)
    await db.flush()
    logger.info("notification_settings_updated", company_id=str(company_id))
    return settings


def is_enabled(settings: CompanyNotificationSettings, key: str) -> bool:
    return bool(getattr(settings, key, True))
