
"""Bridge service: loads WhatsApp credentials from DB and returns configured provider instances.

Follows the same pattern as sicredi_service.py – per-company credential CRUD,
in-memory client cache, and tenant isolation.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WhatsAppProviderType
from app.models.whatsapp_credential import WhatsAppCredential
from app.services.whatsapp.base import WhatsAppProviderBase
from app.services.whatsapp.meta import MetaCloudProvider
from app.services.whatsapp.uazapi import UazapiProvider
from app.utils.exceptions import ResourceNotFoundError
from app.utils.logging import get_logger

logger = get_logger(__name__)

# In-memory provider cache keyed by credential ID
_provider_cache: dict[UUID, WhatsAppProviderBase] = {}


def _build_provider(cred: WhatsAppCredential) -> WhatsAppProviderBase:
    """Instantiate the correct provider adapter from a DB credential."""
    if cred.provider == WhatsAppProviderType.UAZAPI or cred.provider == "UAZAPI":
        if not cred.uazapi_base_url or not cred.uazapi_instance_token:
            raise ValueError("UAZAPI credentials require base_url and instance_token")
        return UazapiProvider(
            base_url=cred.uazapi_base_url,
            instance_token=cred.uazapi_instance_token,
        )
    elif cred.provider == WhatsAppProviderType.META or cred.provider == "META":
        if not cred.meta_waba_id or not cred.meta_phone_number_id or not cred.meta_access_token:
            raise ValueError("Meta credentials require waba_id, phone_number_id, and access_token")
        return MetaCloudProvider(
            waba_id=cred.meta_waba_id,
            phone_number_id=cred.meta_phone_number_id,
            access_token=cred.meta_access_token,
        )
    else:
        raise ValueError(f"Unknown WhatsApp provider: {cred.provider}")


async def get_provider(
    db: AsyncSession,
    company_id: UUID,
    provider_type: Optional[WhatsAppProviderType] = None,
) -> WhatsAppProviderBase:
    """Load the WhatsApp provider for a company.

    If provider_type is given, loads that specific provider.
    Otherwise loads the default (is_default=True) or the only active one.

    Args:
        db: Async database session.
        company_id: Tenant company ID.
        provider_type: Optional specific provider to load.

    Returns:
        A ready-to-use WhatsAppProviderBase instance.

    Raises:
        ResourceNotFoundError: If no matching active credential found.
    """
    query = select(WhatsAppCredential).where(
        WhatsAppCredential.company_id == company_id,
        WhatsAppCredential.is_active == True,
    )

    if provider_type:
        query = query.where(WhatsAppCredential.provider == provider_type)
    else:
        # Prefer the default provider
        query = query.order_by(WhatsAppCredential.is_default.desc())

    result = await db.execute(query)
    cred = result.scalars().first()

    if not cred:
        raise ResourceNotFoundError(
            resource="WhatsAppCredential",
            detail=f"No active WhatsApp credential found for company {company_id}"
            + (f" (provider={provider_type.value})" if provider_type else ""),
        )

    # Reuse cached provider
    if cred.id in _provider_cache:
        return _provider_cache[cred.id]

    provider = _build_provider(cred)
    _provider_cache[cred.id] = provider
    logger.info(
        "whatsapp_provider_loaded",
        company_id=str(company_id),
        provider=cred.provider,
        credential_id=str(cred.id),
    )
    return provider


async def get_credential_by_id(
    db: AsyncSession, credential_id: UUID, company_id: UUID
) -> WhatsAppCredential:
    """Get a specific credential by ID with tenant check."""
    result = await db.execute(
        select(WhatsAppCredential).where(
            WhatsAppCredential.id == credential_id,
            WhatsAppCredential.company_id == company_id,
        )
    )
    cred = result.scalar_one_or_none()
    if not cred:
        raise ResourceNotFoundError(resource="WhatsAppCredential")
    return cred


async def get_provider_by_credential(
    db: AsyncSession, credential_id: UUID, company_id: UUID
) -> WhatsAppProviderBase:
    """Get a provider instance for a specific credential ID."""
    if credential_id in _provider_cache:
        return _provider_cache[credential_id]

    cred = await get_credential_by_id(db, credential_id, company_id)
    if not cred.is_active:
        raise ResourceNotFoundError(
            resource="WhatsAppCredential",
            detail="Credential is not active",
        )
    provider = _build_provider(cred)
    _provider_cache[cred.id] = provider
    return provider


def invalidate_cache(credential_id: UUID) -> None:
    """Remove a cached provider (e.g. after credential update)."""
    _provider_cache.pop(credential_id, None)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def list_credentials(
    db: AsyncSession, company_id: UUID
) -> list[WhatsAppCredential]:
    """List all WhatsApp credentials for a company."""
    result = await db.execute(
        select(WhatsAppCredential)
        .where(WhatsAppCredential.company_id == company_id)
        .order_by(WhatsAppCredential.created_at.desc())
    )
    return list(result.scalars().all())


async def create_credential(
    db: AsyncSession,
    company_id: UUID,
    *,
    provider: WhatsAppProviderType,
    uazapi_base_url: Optional[str] = None,
    uazapi_instance_token: Optional[str] = None,
    meta_waba_id: Optional[str] = None,
    meta_phone_number_id: Optional[str] = None,
    meta_access_token: Optional[str] = None,
    is_default: bool = False,
) -> WhatsAppCredential:
    """Create a new WhatsApp credential for a company.

    Enforces: max 1 credential per provider per company (via DB constraint).
    If is_default, clears default flag on other credentials.
    """
    if is_default:
        await _clear_default(db, company_id)

    cred = WhatsAppCredential(
        company_id=company_id,
        provider=provider,
        is_active=True,
        is_default=is_default,
        uazapi_base_url=uazapi_base_url,
        uazapi_instance_token=uazapi_instance_token,
        meta_waba_id=meta_waba_id,
        meta_phone_number_id=meta_phone_number_id,
        meta_access_token=meta_access_token,
    )
    db.add(cred)
    await db.flush()
    logger.info(
        "whatsapp_credential_created",
        company_id=str(company_id),
        provider=provider.value,
        credential_id=str(cred.id),
    )
    return cred


async def update_credential(
    db: AsyncSession,
    credential_id: UUID,
    company_id: UUID,
    **updates: object,
) -> WhatsAppCredential:
    """Update an existing WhatsApp credential."""
    cred = await get_credential_by_id(db, credential_id, company_id)

    for key, value in updates.items():
        if value is not None and hasattr(cred, key):
            setattr(cred, key, value)

    invalidate_cache(credential_id)
    await db.flush()
    logger.info("whatsapp_credential_updated", credential_id=str(credential_id))
    return cred


async def delete_credential(
    db: AsyncSession, credential_id: UUID, company_id: UUID
) -> None:
    """Soft-delete a WhatsApp credential."""
    cred = await get_credential_by_id(db, credential_id, company_id)
    cred.is_active = False
    cred.is_default = False
    invalidate_cache(credential_id)
    await db.flush()
    logger.info("whatsapp_credential_deactivated", credential_id=str(credential_id))


async def set_default(
    db: AsyncSession, credential_id: UUID, company_id: UUID
) -> WhatsAppCredential:
    """Mark a credential as the default provider for the company."""
    await _clear_default(db, company_id)
    cred = await get_credential_by_id(db, credential_id, company_id)
    cred.is_default = True
    await db.flush()
    logger.info("whatsapp_default_set", credential_id=str(credential_id))
    return cred


async def update_connection_status(
    db: AsyncSession, credential_id: UUID, company_id: UUID, status: str
) -> None:
    """Cache the latest connection status check result."""
    cred = await get_credential_by_id(db, credential_id, company_id)
    cred.connection_status = status
    cred.last_status_check = datetime.now(timezone.utc)
    await db.flush()


async def _clear_default(db: AsyncSession, company_id: UUID) -> None:
    """Clear is_default on all credentials of a company."""
    await db.execute(
        sa_update(WhatsAppCredential)
        .where(
            WhatsAppCredential.company_id == company_id,
            WhatsAppCredential.is_default == True,
        )
        .values(is_default=False)
    )
