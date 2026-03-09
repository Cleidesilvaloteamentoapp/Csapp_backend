from typing import Optional

"""Client business-logic service."""

import math
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.core.tenant import get_tenant_filter
from app.models.client import Client
from app.models.enums import ClientStatus, UserRole
from app.models.user import Profile
from app.schemas.client import ClientCreate, ClientUpdate, ClientResponse
from app.schemas.common import PaginatedResponse, PaginationParams
from app.utils.exceptions import ResourceNotFoundError, TenantIsolationError
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def list_clients(
    db: AsyncSession,
    company_id: UUID,
    params: PaginationParams,
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
) -> PaginatedResponse[ClientResponse]:
    """Paginated list of clients for the current tenant."""
    base = select(Client).where(Client.company_id == company_id)

    if status_filter:
        base = base.where(Client.status == status_filter)
    if search:
        pattern = f"%{search}%"
        base = base.where(
            (Client.full_name.ilike(pattern)) | (Client.cpf_cnpj.ilike(pattern))
        )

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    rows = await db.execute(
        base.order_by(Client.created_at.desc())
        .offset(params.offset)
        .limit(params.per_page)
    )
    items = [ClientResponse.model_validate(r) for r in rows.scalars().all()]

    return PaginatedResponse[ClientResponse](
        items=items,
        total=total,
        page=params.page,
        per_page=params.per_page,
        pages=math.ceil(total / params.per_page) if params.per_page else 0,
    )


async def create_client(
    db: AsyncSession,
    company_id: UUID,
    creator_id: UUID,
    data: ClientCreate,
) -> Client:
    """Create a new client; optionally create a login profile."""
    client = Client(
        company_id=company_id,
        email=data.email,
        full_name=data.full_name,
        cpf_cnpj=data.cpf_cnpj,
        phone=data.phone,
        contract_number=data.contract_number,
        matricula=data.matricula,
        address=data.address,
        notes=data.notes,
        status=ClientStatus.ACTIVE,
        created_by=creator_id,
    )

    if data.create_access and data.password:
        profile = Profile(
            company_id=company_id,
            role=UserRole.CLIENT,
            full_name=data.full_name,
            email=data.email,
            cpf_cnpj=data.cpf_cnpj,
            phone=data.phone,
            hashed_password=hash_password(data.password),
        )
        db.add(profile)
        await db.flush()
        client.profile_id = profile.id

    db.add(client)
    await db.flush()
    logger.info("client_created", client_id=str(client.id), company_id=str(company_id))
    return client


async def get_client(db: AsyncSession, company_id: UUID, client_id: UUID) -> Client:
    """Retrieve a single client with tenant isolation."""
    result = await db.execute(
        select(Client).where(Client.id == client_id, Client.company_id == company_id)
    )
    client = result.scalar_one_or_none()
    if client is None:
        raise ResourceNotFoundError("Client")
    return client


async def update_client(
    db: AsyncSession, company_id: UUID, client_id: UUID, data: ClientUpdate
) -> Client:
    """Partial update of client data."""
    client = await get_client(db, company_id, client_id)
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(client, field, value)
    await db.flush()
    logger.info("client_updated", client_id=str(client_id))
    return client


async def deactivate_client(db: AsyncSession, company_id: UUID, client_id: UUID) -> Client:
    """Soft-delete: set client status to inactive."""
    client = await get_client(db, company_id, client_id)
    client.status = ClientStatus.INACTIVE
    await db.flush()
    logger.info("client_deactivated", client_id=str(client_id))
    return client
