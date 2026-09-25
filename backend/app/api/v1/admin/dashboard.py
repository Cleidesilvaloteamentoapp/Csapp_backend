
"""Admin dashboard endpoints."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, extract, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_company_admin, require_permission, scoped_company
from app.models.audit import AuditLog
from app.models.batch_operation import BatchOperation
from app.models.boleto import Boleto
from app.models.client import Client
from app.models.client_document import ClientDocument
from app.models.client_lot import ClientLot
from app.models.contract_transfer import ContractTransfer
from app.models.cycle_approval import CycleApproval
from app.models.early_payoff_request import EarlyPayoffRequest
from app.models.enums import (
    BoletoStatus,
    ClientLotStatus,
    ClientStatus,
    CycleApprovalStatus,
    DocumentStatus,
    EarlyPayoffStatus,
    InvoiceStatus,
    LotStatus,
    RenegotiationStatus,
    RescissionStatus,
    ServiceOrderStatus,
    ServiceRequestStatus,
    TransferStatus,
)
from app.models.invoice import Invoice
from app.models.lot import Lot
from app.models.renegotiation import Renegotiation
from app.models.rescission import Rescission
from app.models.service import ServiceOrder, ServiceType
from app.models.service_request import ServiceRequest
from app.models.sicredi_event import SicrediEvent
from app.models.user import Profile
from app.schemas.dashboard import (
    ActionQueue,
    ActionQueueItem,
    AdminStats,
    BillingPipeline,
    BoletoStatusCount,
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
    cid: UUID = Depends(scoped_company),
):
    """General statistics for the admin dashboard."""

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
    cid: UUID = Depends(scoped_company),
):
    """Financial summary: receivable, received, overdue."""

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
    cid: UUID = Depends(scoped_company),
):
    """Most recent operations for the company, sourced from the audit trail."""

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
    cid: UUID = Depends(scoped_company),
):
    """Monthly revenue for the last N months (chronological, gaps filled with 0)."""
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
    cid: UUID = Depends(scoped_company),
):
    """Most requested service types."""
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
    cid: UUID = Depends(scoped_company),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List defaulter clients with overdue details (drill-down from dashboard card)."""
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


@router.get("/action-queue", response_model=ActionQueue)
async def action_queue(
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_financial")),
    cid: UUID = Depends(scoped_company),
):
    """Everything waiting on a human decision, in one round-trip.

    The dashboard is the control panel, so each tile carries its own plain
    instruction and a link to the screen already filtered to those rows --
    counting is not the point, acting on the count is.
    """

    async def _count(model, *where) -> int:
        return (await db.execute(
            select(func.count()).select_from(model).where(model.company_id == cid, *where)
        )).scalar() or 0

    cycles_pending = await _count(
        CycleApproval, CycleApproval.status == CycleApprovalStatus.PENDING
    )
    cycles_final = await _count(
        CycleApproval,
        CycleApproval.status == CycleApprovalStatus.PENDING,
        CycleApproval.is_final_cycle.is_(True),
    )
    cycles_blocked = await _count(
        CycleApproval,
        CycleApproval.status == CycleApprovalStatus.PENDING,
        CycleApproval.unpaid_count > 0,
    )
    transfers = await _count(
        ContractTransfer, ContractTransfer.status == TransferStatus.PENDING
    )
    rescissions = await _count(
        Rescission,
        Rescission.status.in_([
            RescissionStatus.REQUESTED, RescissionStatus.PENDING_APPROVAL
        ]),
    )
    early_payoff = await _count(
        EarlyPayoffRequest, EarlyPayoffRequest.status == EarlyPayoffStatus.PENDING
    )
    renegotiations = await _count(
        Renegotiation, Renegotiation.status == RenegotiationStatus.PENDING_APPROVAL
    )
    documents = await _count(
        ClientDocument, ClientDocument.status == DocumentStatus.PENDING_REVIEW
    )
    requests_open = await _count(
        ServiceRequest,
        ServiceRequest.status.in_([
            ServiceRequestStatus.OPEN, ServiceRequestStatus.IN_PROGRESS
        ]),
    )

    items = [
        ActionQueueItem(
            key="cycle_approvals",
            label="Renovações de ciclo",
            count=cycles_pending,
            hint=(
                "Contratos que chegaram ao fim das 12 parcelas. Aprove para gerar "
                "o próximo carnê com o reajuste."
                + (
                    f" {cycles_blocked} com parcela em aberto — use 'Renovar agora'."
                    if cycles_blocked
                    else ""
                )
            ),
            href="/admin/cycle-approvals?status=PENDING",
            severity="critical" if cycles_pending else "info",
        ),
        ActionQueueItem(
            key="final_cycles",
            label="Último ciclo — escrituração",
            count=cycles_final,
            hint=(
                "Contratos no último ciclo. Inicie a escrituração: o checklist de "
                "documentos já está aberto."
            ),
            href="/admin/cycle-approvals?status=PENDING&final=1",
            severity="warning" if cycles_final else "info",
        ),
        ActionQueueItem(
            key="transfers",
            label="Transferências de contrato",
            count=transfers,
            hint="Trocas de titularidade aguardando aprovação.",
            href="/admin/transfers?status=PENDING",
            severity="warning" if transfers else "info",
        ),
        ActionQueueItem(
            key="rescissions",
            label="Distratos",
            count=rescissions,
            hint="Pedidos de rescisão aguardando análise.",
            href="/admin/rescissions?status=PENDING_APPROVAL",
            severity="warning" if rescissions else "info",
        ),
        ActionQueueItem(
            key="early_payoff",
            label="Quitações antecipadas",
            count=early_payoff,
            hint="Clientes que pediram para quitar o saldo devedor.",
            href="/admin/early-payoff-requests?status=PENDING",
            severity="info",
        ),
        ActionQueueItem(
            key="renegotiations",
            label="Renegociações",
            count=renegotiations,
            hint="Acordos aguardando aprovação antes de virar boleto.",
            href="/admin/financial?tab=renegotiations",
            severity="warning" if renegotiations else "info",
        ),
        ActionQueueItem(
            key="documents",
            label="Documentos a revisar",
            count=documents,
            hint="Documentos enviados pelos clientes aguardando conferência.",
            href="/admin/documents?status=PENDING_REVIEW",
            severity="info",
        ),
        ActionQueueItem(
            key="service_requests",
            label="Solicitações abertas",
            count=requests_open,
            hint="Atendimentos em aberto no portal do cliente.",
            href="/admin/service-requests?status=OPEN",
            severity="info",
        ),
    ]

    return ActionQueue(items=items, total=sum(i.count for i in items))


@router.get("/billing-pipeline", response_model=BillingPipeline)
async def billing_pipeline(
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("view_financial")),
    cid: UUID = Depends(scoped_company),
):
    """Health of the billing chain, from invoice to registered boleto.

    An installment with no boleto will never be paid, and an unpaid installment
    holds its contract's whole cycle shut -- so this is the number that explains
    why a renewal is stuck.
    """
    now = datetime.now(timezone.utc)

    no_boleto = (await db.execute(
        select(
            func.count(Invoice.id),
            func.coalesce(func.sum(Invoice.amount), 0),
        ).where(
            Invoice.company_id == cid,
            Invoice.status.in_([InvoiceStatus.PENDING, InvoiceStatus.OVERDUE]),
            ~Invoice.id.in_(
                select(Boleto.invoice_id).where(
                    Boleto.invoice_id.is_not(None),
                    Boleto.status != BoletoStatus.CANCELADO,
                )
            ),
        )
    )).one()

    status_rows = (await db.execute(
        select(
            Boleto.status,
            func.count(Boleto.id),
            func.coalesce(func.sum(Boleto.valor), 0),
        )
        .where(Boleto.company_id == cid)
        .group_by(Boleto.status)
    )).all()

    in_progress = (await db.execute(
        select(func.count()).select_from(BatchOperation).where(
            BatchOperation.company_id == cid,
            BatchOperation.status.in_(["PENDING", "PROCESSING"]),
        )
    )).scalar() or 0

    week_ago = now - timedelta(days=7)
    failed_recent = (await db.execute(
        select(func.count()).select_from(BatchOperation).where(
            BatchOperation.company_id == cid,
            BatchOperation.status == "FAILED",
            BatchOperation.created_at >= week_ago,
        )
    )).scalar() or 0

    last_sync = (await db.execute(
        select(func.max(SicrediEvent.created_at)).where(
            SicrediEvent.company_id == cid,
            SicrediEvent.success.is_(True),
        )
    )).scalar()

    day_ago = now - timedelta(days=1)
    errors_24h = (await db.execute(
        select(func.count()).select_from(SicrediEvent).where(
            SicrediEvent.company_id == cid,
            SicrediEvent.success.is_(False),
            SicrediEvent.created_at >= day_ago,
        )
    )).scalar() or 0

    return BillingPipeline(
        invoices_without_boleto=no_boleto[0] or 0,
        invoices_without_boleto_amount=Decimal(str(no_boleto[1])),
        boletos_by_status=[
            BoletoStatusCount(
                status=r[0].value if hasattr(r[0], "value") else str(r[0]),
                count=r[1],
                total_value=Decimal(str(r[2])),
            )
            for r in status_rows
        ],
        batches_in_progress=in_progress,
        batches_failed_recently=failed_recent,
        last_sicredi_sync=last_sync,
        sicredi_errors_24h=errors_24h,
    )

