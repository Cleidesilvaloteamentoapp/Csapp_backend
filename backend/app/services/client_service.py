from typing import Optional

"""Client business-logic service."""

import math
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.core.tenant import get_tenant_filter
from app.models.client import Client
from app.models.client_lot import ClientLot
from app.models.enums import ClientLotStatus, ClientStatus, LotStatus, UserRole
from app.models.lot import Lot
from app.models.user import Profile
from app.schemas.client import ClientCreate, ClientUpdate, ClientResponse
from app.schemas.common import PaginatedResponse, PaginationParams
from app.utils.documents import normalize_cpf_cnpj
from app.utils.exceptions import ResourceNotFoundError, TenantIsolationError
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Postgres expression that strips any non-digit from a stored CPF/CNPJ, so the
# uniqueness check matches regardless of how legacy rows were formatted.
_CPF_DIGITS = func.regexp_replace(Client.cpf_cnpj, r"\D", "", "g")


async def find_client_by_cpf(
    db: AsyncSession,
    company_id: UUID,
    cpf_cnpj: str,
    exclude_id: Optional[UUID] = None,
) -> Optional[Client]:
    """Return an existing client in this company with the same CPF/CNPJ.

    Comparison is done on digits only, so "123.456.789-00" and "12345678900"
    are recognised as the same document. Returns None when the CPF is empty
    or no match exists.
    """
    digits = normalize_cpf_cnpj(cpf_cnpj)
    if not digits:
        return None
    query = select(Client).where(
        Client.company_id == company_id,
        _CPF_DIGITS == digits,
    )
    if exclude_id is not None:
        query = query.where(Client.id != exclude_id)
    return (await db.execute(query.limit(1))).scalars().first()


async def _fire_admin_notify(db, company_id, key, title, message, n_type, data=None):
    """Deferred import to avoid circular imports at module load."""
    try:
        from app.services.admin_notify_service import notify_admins
        from app.models.enums import NotificationType as NT
        await notify_admins(db, company_id, key, title=title, message=message, n_type=n_type, data=data or {})
    except Exception as exc:
        logger.warning("client_admin_notify_failed", error=str(exc))


async def list_clients(
    db: AsyncSession,
    company_id: UUID,
    params: PaginationParams,
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
) -> PaginatedResponse[ClientResponse]:
    """Paginated list of clients for the current tenant."""
    base = select(Client).where(Client.company_id == company_id)

    if status_filter and status_filter.lower() != "all":
        try:
            enum_val = ClientStatus(status_filter.upper())
            base = base.where(Client.status == enum_val)
        except ValueError:
            pass
    if search:
        pattern = f"%{search}%"
        base = base.where(
            (Client.full_name.ilike(pattern))
            | (Client.cpf_cnpj.ilike(pattern))
            | (Client.email.ilike(pattern))
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
    # Trava de duplicidade: bloqueia CPF/CNPJ já cadastrado nesta empresa,
    # independentemente de criar (ou não) acesso ao portal. A comparação é
    # feita por dígitos, então formatações diferentes não escapam da trava.
    existing = await find_client_by_cpf(db, company_id, data.cpf_cnpj)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="CPF/CNPJ já cadastrado para outro cliente. Verifique se o cliente já existe.",
        )

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
        try:
            await db.flush()
        except IntegrityError as e:
            await db.rollback()
            error_msg = str(e.orig) if e.orig else str(e)
            if "cpf_cnpj" in error_msg or "ix_profiles_cpf_cnpj" in error_msg:
                raise HTTPException(
                    status_code=409,
                    detail="CPF/CNPJ já cadastrado. Verifique se o cliente já existe."
                )
            elif "email" in error_msg or "ix_profiles_email" in error_msg:
                raise HTTPException(
                    status_code=409,
                    detail="E-mail já cadastrado. Verifique se o cliente já existe."
                )
            else:
                raise HTTPException(
                    status_code=409,
                    detail="Dado duplicado. Verifique se o cliente já existe."
                )
        client.profile_id = profile.id

    db.add(client)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        error_msg = str(e.orig) if e.orig else str(e)
        if "cpf_cnpj" in error_msg or "ix_clients_cpf_cnpj" in error_msg:
            raise HTTPException(
                status_code=409,
                detail="CPF/CNPJ já cadastrado. Verifique se o cliente já existe."
            )
        elif "email" in error_msg or "ix_clients_email" in error_msg:
            raise HTTPException(
                status_code=409,
                detail="E-mail já cadastrado. Verifique se o cliente já existe."
            )
        else:
            raise HTTPException(
                status_code=409,
                detail="Dado duplicado. Verifique se o cliente já existe."
            )
    logger.info("client_created", client_id=str(client.id), company_id=str(company_id))

    from app.models.enums import NotificationType
    await _fire_admin_notify(
        db, company_id, "notify_admin_client_created",
        title="Novo cliente cadastrado",
        message=f"Cliente {client.full_name} foi cadastrado no sistema.",
        n_type=NotificationType.CLIENTE_CADASTRADO,
        data={"client_id": str(client.id), "name": client.full_name},
    )

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

    # Trava de duplicidade ao trocar o CPF/CNPJ para um já usado por outro cliente.
    new_cpf = update_data.get("cpf_cnpj")
    if new_cpf:
        clash = await find_client_by_cpf(db, company_id, new_cpf, exclude_id=client_id)
        if clash is not None:
            raise HTTPException(
                status_code=409,
                detail="CPF/CNPJ já cadastrado para outro cliente. Verifique se o cliente já existe.",
            )

    for field, value in update_data.items():
        setattr(client, field, value)
    await db.flush()
    logger.info("client_updated", client_id=str(client_id))
    return client


async def deactivate_client(db: AsyncSession, company_id: UUID, client_id: UUID) -> Client:
    """Soft-delete a client: mark inactive, release lots, drop portal account.

    Releasing the lots (active ClientLot -> CANCELLED, Lot -> AVAILABLE) prevents
    the lot from being stuck as SOLD/orphaned. Deleting the linked portal Profile
    frees the unique email/CPF so the client can be re-registered later.
    """
    client = await get_client(db, company_id, client_id)
    client.status = ClientStatus.INACTIVE

    # Release any active contracts and free the underlying lots.
    active_lots = (await db.execute(
        select(ClientLot).where(
            ClientLot.client_id == client_id,
            ClientLot.status == ClientLotStatus.ACTIVE,
        )
    )).scalars().all()
    for cl in active_lots:
        cl.status = ClientLotStatus.CANCELLED
        lot = (await db.execute(select(Lot).where(Lot.id == cl.lot_id))).scalar_one_or_none()
        if lot is not None and lot.status != LotStatus.AVAILABLE:
            lot.status = LotStatus.AVAILABLE

    # Remove the portal account tied to this client (frees the unique email/CPF).
    if client.profile_id is not None:
        profile = (await db.execute(
            select(Profile).where(Profile.id == client.profile_id)
        )).scalar_one_or_none()
        if profile is not None:
            client.profile_id = None  # FK is SET NULL; clear before delete
            await db.flush()
            await db.delete(profile)

    await db.flush()
    logger.info(
        "client_deactivated",
        client_id=str(client_id),
        lots_released=len(active_lots),
    )

    from app.models.enums import NotificationType
    await _fire_admin_notify(
        db, company_id, "notify_admin_client_deleted",
        title="Cliente excluído",
        message=f"Cliente {client.full_name} foi desativado. {len(active_lots)} lote(s) liberado(s).",
        n_type=NotificationType.CLIENTE_EXCLUIDO,
        data={"client_id": str(client_id), "name": client.full_name, "lots_released": len(active_lots)},
    )

    return client
