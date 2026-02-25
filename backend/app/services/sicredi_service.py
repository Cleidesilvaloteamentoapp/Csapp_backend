
"""Application-level service that bridges database-stored credentials with the Sicredi module.

This service handles:
- Loading SicrediCredential from DB per company (tenant isolation)
- Converting DB model to SicrediCredentials dataclass
- Providing a ready-to-use SicrediClient instance
- CRUD operations for credential management
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sicredi_credential import SicrediCredential
from app.services.sicredi import SicrediClient, SicrediCredentials, SicrediEnvironment
from app.utils.exceptions import ResourceNotFoundError
from app.utils.logging import get_logger

logger = get_logger(__name__)

# In-memory client cache keyed by credential ID to reuse token state
_client_cache: dict[UUID, SicrediClient] = {}


async def get_sicredi_client(db: AsyncSession, company_id: UUID) -> SicrediClient:
    """Load the active Sicredi credential for a company and return a configured client.

    Caches client instances to preserve token state across requests.

    Args:
        db: Async database session.
        company_id: The tenant company ID.

    Returns:
        A ready-to-use SicrediClient.

    Raises:
        ResourceNotFoundError: If no active credential is found for the company.
    """
    result = await db.execute(
        select(SicrediCredential).where(
            SicrediCredential.company_id == company_id,
            SicrediCredential.is_active == True,
        )
    )
    cred = result.scalar_one_or_none()

    if not cred:
        raise ResourceNotFoundError(
            resource="SicrediCredential",
            detail=f"No active Sicredi credentials found for company {company_id}",
        )

    # Reuse cached client if credential ID matches
    if cred.id in _client_cache:
        return _client_cache[cred.id]

    env = SicrediEnvironment(cred.environment) if cred.environment in ("sandbox", "production") else SicrediEnvironment.PRODUCTION

    credentials = SicrediCredentials(
        x_api_key=cred.x_api_key,
        username=cred.username,
        password=cred.password,
        cooperativa=cred.cooperativa,
        posto=cred.posto,
        codigo_beneficiario=cred.codigo_beneficiario,
        environment=env,
    )

    # Restore cached tokens from DB if available
    if cred.access_token and cred.token_expires_at:
        credentials._access_token = cred.access_token
        credentials._refresh_token = cred.refresh_token
        credentials._token_expires_at = cred.token_expires_at.timestamp() if cred.token_expires_at else None
        credentials._refresh_expires_at = cred.refresh_expires_at.timestamp() if cred.refresh_expires_at else None

    client = SicrediClient(credentials=credentials)
    _client_cache[cred.id] = client

    logger.info("sicredi_client_loaded", company_id=str(company_id), credential_id=str(cred.id))
    return client


async def persist_token_cache(db: AsyncSession, company_id: UUID) -> None:
    """Save the current in-memory token state back to the database.

    Should be called after operations that may have refreshed the token.
    """
    result = await db.execute(
        select(SicrediCredential).where(
            SicrediCredential.company_id == company_id,
            SicrediCredential.is_active == True,
        )
    )
    cred = result.scalar_one_or_none()
    if not cred or cred.id not in _client_cache:
        return

    client = _client_cache[cred.id]
    creds = client.credentials

    if creds._access_token:
        cred.access_token = creds._access_token
        cred.refresh_token = creds._refresh_token
        cred.token_expires_at = (
            datetime.fromtimestamp(creds._token_expires_at, tz=timezone.utc)
            if creds._token_expires_at else None
        )
        cred.refresh_expires_at = (
            datetime.fromtimestamp(creds._refresh_expires_at, tz=timezone.utc)
            if creds._refresh_expires_at else None
        )
        await db.flush()


def invalidate_client_cache(credential_id: UUID) -> None:
    """Remove a cached client (e.g. after credential update)."""
    _client_cache.pop(credential_id, None)


# ---------------------------------------------------------------------------
# Credential CRUD
# ---------------------------------------------------------------------------

async def create_credential(
    db: AsyncSession,
    company_id: UUID,
    *,
    x_api_key: str,
    username: str,
    password: str,
    cooperativa: str,
    posto: str,
    codigo_beneficiario: str,
    environment: str = "production",
) -> SicrediCredential:
    """Create a new Sicredi credential for a company."""
    cred = SicrediCredential(
        company_id=company_id,
        x_api_key=x_api_key,
        username=username,
        password=password,
        cooperativa=cooperativa,
        posto=posto,
        codigo_beneficiario=codigo_beneficiario,
        environment=environment,
    )
    db.add(cred)
    await db.flush()
    logger.info("sicredi_credential_created", company_id=str(company_id), credential_id=str(cred.id))
    return cred


async def update_credential(
    db: AsyncSession,
    credential_id: UUID,
    company_id: UUID,
    **updates,
) -> SicrediCredential:
    """Update an existing Sicredi credential."""
    result = await db.execute(
        select(SicrediCredential).where(
            SicrediCredential.id == credential_id,
            SicrediCredential.company_id == company_id,
        )
    )
    cred = result.scalar_one_or_none()
    if not cred:
        raise ResourceNotFoundError(resource="SicrediCredential")

    for key, value in updates.items():
        if value is not None and hasattr(cred, key):
            setattr(cred, key, value)

    # Invalidate cached client so it gets rebuilt with new credentials
    invalidate_client_cache(credential_id)

    await db.flush()
    logger.info("sicredi_credential_updated", credential_id=str(credential_id))
    return cred


async def get_credential(db: AsyncSession, company_id: UUID) -> Optional[SicrediCredential]:
    """Get the active Sicredi credential for a company."""
    result = await db.execute(
        select(SicrediCredential).where(
            SicrediCredential.company_id == company_id,
            SicrediCredential.is_active == True,
        )
    )
    return result.scalar_one_or_none()


async def delete_credential(db: AsyncSession, credential_id: UUID, company_id: UUID) -> None:
    """Deactivate (soft delete) a Sicredi credential."""
    result = await db.execute(
        select(SicrediCredential).where(
            SicrediCredential.id == credential_id,
            SicrediCredential.company_id == company_id,
        )
    )
    cred = result.scalar_one_or_none()
    if not cred:
        raise ResourceNotFoundError(resource="SicrediCredential")

    cred.is_active = False
    invalidate_client_cache(credential_id)
    await db.flush()
    logger.info("sicredi_credential_deactivated", credential_id=str(credential_id))
