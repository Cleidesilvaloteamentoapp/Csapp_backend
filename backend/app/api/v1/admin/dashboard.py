
"""Admin dashboard endpoints."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, extract, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_company_admin, require_permission
from app.models.audit import AuditLog
from app.models.client import Client
from app.models.client_lot import ClientLot
from app.models.enums import (
    ClientLotStatus,
    ClientStatus,
    InvoiceStatus,
    LotStatus,
    ServiceOrderStatus,
)
from app.models.invoice import Invoice
from app.models.lot import Lot
from app.models.service import ServiceOrder, ServiceType
from app.models.user import Profile
from app.schemas.dashboard import (
    AdminStats,
    DefaulterDetailResponse,
    FinancialOverview,
    RecentActivity,
    RevenueChartPoint,
    ServiceChartPoint,
)

# Human-readable labels for audit entries, keyed by the audited table. Used to
# turn the raw audit trail into friendly "recent activity" rows on the dashboard.
_ACTIVITY_LABELS: dict[str, str] = {
    "clients": "Cliente",
    "client_lots": "Contrato",
    "invoices": "Fatura",
    "boletos": "Boleto",
    "batch_operations": "Lote de boletos",
    "renegotiations": "Renegociação",
    "rescissions": "Distrato",
    "contract_history": "Contrato",
    "contract_transfers": "Transferência de contrato",
    "sicredi_credentials": "Credencial Sicredi",
    "profiles": "Usuário",
    "client_documents": "Documento",
    "service_requests": "Solicitação",
    "economic_indices": "Índice econômico",
    "cycle_approvals": "Aprovação de ciclo",
    "early_payoff_requests": "Quitação antecipada",
    "whatsapp_credentials": "Credencial WhatsApp",
    "developments": "Empreendimento",
    "lots": "Lote",
}

_OPERATION_LABELS: dict[str, str] = {
    "CREATE": "criado(a)",
    "UPDATE": "atualizado(a)",
    "DELETE": "excluído(a)",
    "READ": "consultado(a)",
}


def _activity_label(table_name: str, operation: str) -> str:
    """Friendly type label for an audit row, e.g. 'Cliente' / 'Contrato'."""
    return _ACTIVITY_LABELS.get(table_name, table_name)


def _activity_description(entry: AuditLog) -> str:
    """Prefer the stored (already Portuguese) detail; otherwise synthesize one."""
    if entry.detail:
        return entry.detail
    noun = _ACTIVITY_LABELS.get(entry.table_name, entry.table_name)
    verb = _OPERATION_LABELS.get(entry.operation, entry.operation.lower())
    return f"{noun} {verb}"

router = APIRouter(prefix="/dashboard", tags=["Admin Dashboard"])


@router.get("/stats", response_model=AdminStats)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_financial")),
):
    """General statistics for the admin dashboard."""
    cid = admin.company_id

    total_clients = (await db.execute(
        select(func.count()).where(Client.company_id == cid)
    )).scalar() or 0

    active_clients = (await db.execute(
        select(func.count()).where(Client.company_id == cid, Client.status == ClientStatus.ACTIVE)
    )).scalar() or 0

    defaulter_clients = (await db.execute(
        select(func.count()).where(Client.company_id == cid, Client.status == ClientStatus.DEFAULTER)
    )).scalar() or 0

    inactive_clients = (await db.execute(
        select(func.count()).where(Client.company_id == cid, Client.status == ClientStatus.INACTIVE)
    )).scalar() or 0

    in_negotiation_clients = (await db.execute(
        select(func.count()).where(Client.company_id == cid, Client.status == ClientStatus.IN_NEGOTIATION)
    )).scalar() or 0

    # New clients registered in the current calendar month.
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    new_clients_this_month = (await db.execute(
        select(func.count()).where(
            Client.company_id == cid,
            Client.created_at >= month_start,
        )
    )).scalar() or 0

    # Active contracts (client_lots currently ACTIVE).
    active_contracts = (await db.execute(
        select(func.count()).where(
            ClientLot.company_id == cid,
            ClientLot.status == ClientLotStatus.ACTIVE,
        )
    )).scalar() or 0

    open_orders = (await db.execute(
        select(func.count()).where(
            ServiceOrder.company_id == cid,
            ServiceOrder.status.in_([
                ServiceOrderStatus.REQUESTED,
                ServiceOrderStatus.APPROVED,
                ServiceOrderStatus.IN_PROGRESS,
            ]),
        )
    )).scalar() or 0

    completed_orders = (await db.execute(
        select(func.count()).where(
            ServiceOrder.company_id == cid,
            ServiceOrder.status == ServiceOrderStatus.COMPLETED,
        )
    )).scalar() or 0

    total_lots = (await db.execute(
        select(func.count()).where(Lot.company_id == cid)
    )).scalar() or 0

    available_lots = (await db.execute(
        select(func.count()).where(Lot.company_id == cid, Lot.status == LotStatus.AVAILABLE)
    )).scalar() or 0

    reserved_lots = (await db.execute(
        select(func.count()).where(Lot.company_id == cid, Lot.status == LotStatus.RESERVED)
    )).scalar() or 0

    sold_lots = (await db.execute(
        select(func.count()).where(Lot.company_id == cid, Lot.status == LotStatus.SOLD)
    )).scalar() or 0

    return AdminStats(
        total_clients=total_clients,
        active_clients=active_clients,
        defaulter_clients=defaulter_clients,
        inactive_clients=inactive_clients,
        in_negotiation_clients=in_negotiation_clients,
        new_clients_this_month=new_clients_this_month,
        active_contracts=active_contracts,
        open_service_orders=open_orders,
        completed_service_orders=completed_orders,
        total_lots=total_lots,
        available_lots=available_lots,
        reserved_lots=reserved_lots,
        sold_lots=sold_lots,
    )


@router.get("/financial-overview", response_model=FinancialOverview)
async def financial_overview(
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_financial")),
):
    """Financial summary: receivable, received, overdue."""
    cid = admin.company_id

    total_receivable = (await db.execute(
        select(func.coalesce(func.sum(Invoice.amount), 0)).where(
            Invoice.company_id == cid,
            Invoice.status == InvoiceStatus.PENDING,
        )
    )).scalar()

    total_received = (await db.execute(
        select(func.coalesce(func.sum(Invoice.amount), 0)).where(
            Invoice.company_id == cid,
            Invoice.status == InvoiceStatus.PAID,
        )
    )).scalar()

    overdue_q = select(
        func.coalesce(func.sum(Invoice.amount), 0),
        func.count(),
    ).where(
        Invoice.company_id == cid,
        Invoice.status == InvoiceStatus.OVERDUE,
    )
    row = (await db.execute(overdue_q)).one()

    # Pending invoices coming due within the next 7 days (upcoming collections).
    today = datetime.now(timezone.utc).date()
    due_soon_q = select(
        func.coalesce(func.sum(Invoice.amount), 0),
        func.count(),
    ).where(
        Invoice.company_id == cid,
        Invoice.status == InvoiceStatus.PENDING,
        Invoice.due_date >= today,
        Invoice.due_date <= today + timedelta(days=7),
    )
    due_soon = (await db.execute(due_soon_q)).one()

    return FinancialOverview(
        total_receivable=Decimal(str(total_receivable)),
        total_received=Decimal(str(total_received)),
        total_overdue=Decimal(str(row[0])),
        overdue_count=row[1],
        due_soon_amount=Decimal(str(due_soon[0])),
        due_soon_count=due_soon[1],
    )


@router.get("/recent-activities", response_model=list[RecentActivity])
async def recent_activities(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_financial")),
):
    """Most recent operations for the company, sourced from the audit trail."""
    cid = admin.company_id

    rows = (await db.execute(
        select(AuditLog)
        .where(AuditLog.company_id == cid)
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
    )).scalars().all()

    return [
        RecentActivity(
            id=entry.id,
            type=_activity_label(entry.table_name, entry.operation),
            description=_activity_description(entry),
            created_at=entry.timestamp,
        )
        for entry in rows
    ]


@router.get("/charts/revenue", response_model=list[RevenueChartPoint])
async def revenue_chart(
    months: int = Query(6, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_financial")),
):
    """Monthly revenue for the last N months (chronological, gaps filled with 0)."""
    cid = admin.company_id
    now = datetime.now(timezone.utc)

    # First day of the month, (months - 1) months back — the window start.
    start_index = (now.year * 12 + now.month - 1) - (months - 1)
    start_year, start_month = divmod(start_index, 12)
    start_month += 1
    cutoff = datetime(start_year, start_month, 1, tzinfo=timezone.utc)

    q = (
        select(
            extract("year", Invoice.paid_at).label("yr"),
            extract("month", Invoice.paid_at).label("mo"),
            func.coalesce(func.sum(Invoice.amount), 0).label("total"),
        )
        .where(
            Invoice.company_id == cid,
            Invoice.status == InvoiceStatus.PAID,
            Invoice.paid_at.isnot(None),
            Invoice.paid_at >= cutoff,
        )
        .group_by("yr", "mo")
        .order_by("yr", "mo")
    )
    rows = (await db.execute(q)).all()
    totals = {f"{int(r.yr)}-{int(r.mo):02d}": Decimal(str(r.total)) for r in rows}

    # Emit every month in the window so the chart has a continuous X axis.
    points: list[RevenueChartPoint] = []
    for offset in range(months):
        idx = start_index + offset
        yr, mo = divmod(idx, 12)
        mo += 1
        key = f"{yr}-{mo:02d}"
        points.append(RevenueChartPoint(month=key, amount=totals.get(key, Decimal("0"))))
    return points


@router.get("/charts/services", response_model=list[ServiceChartPoint])
async def services_chart(
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_financial")),
):
    """Most requested service types."""
    cid = admin.company_id
    q = (
        select(ServiceType.name, func.count(ServiceOrder.id).label("cnt"))
        .join(ServiceOrder, ServiceOrder.service_type_id == ServiceType.id)
        .where(ServiceType.company_id == cid)
        .group_by(ServiceType.name)
        .order_by(func.count(ServiceOrder.id).desc())
        .limit(10)
    )
    rows = (await db.execute(q)).all()
    return [ServiceChartPoint(service_name=r[0], count=r[1]) for r in rows]


@router.get("/defaulters", response_model=list[DefaulterDetailResponse])
async def list_defaulters(
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_financial")),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List defaulter clients with overdue details (drill-down from dashboard card)."""
    cid = admin.company_id
    today = datetime.now(timezone.utc).date()

    q = (
        select(
            Client.id.label("client_id"),
            Client.full_name.label("client_name"),
            Client.cpf_cnpj.label("cpf_cnpj"),
            Client.phone.label("phone"),
            func.count(Invoice.id).label("overdue_invoices"),
            func.coalesce(func.sum(Invoice.amount), 0).label("overdue_amount"),
            func.min(Invoice.due_date).label("oldest_due_date"),
        )
        .join(ClientLot, ClientLot.client_id == Client.id)
        .join(Invoice, Invoice.client_lot_id == ClientLot.id)
        .where(
            Client.company_id == cid,
            Client.status == ClientStatus.DEFAULTER,
            Invoice.status == InvoiceStatus.OVERDUE,
        )
        .group_by(Client.id, Client.full_name, Client.cpf_cnpj, Client.phone)
        .order_by(func.min(Invoice.due_date).asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(q)).all()

    return [
        DefaulterDetailResponse(
            client_id=r.client_id,
            client_name=r.client_name,
            cpf_cnpj=r.cpf_cnpj,
            phone=r.phone,
            overdue_invoices=r.overdue_invoices,
            overdue_amount=Decimal(str(r.overdue_amount)),
            oldest_due_date=r.oldest_due_date,
            days_overdue=(today - r.oldest_due_date).days if r.oldest_due_date else 0,
        )
        for r in rows
    ]
