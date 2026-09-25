from typing import Optional

"""Dashboard and financial overview schemas."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Admin Dashboard
# ---------------------------------------------------------------------------

class AdminStats(BaseModel):
    """High-level stats for the admin dashboard."""

    total_clients: int = 0
    active_clients: int = 0
    defaulter_clients: int = 0
    # Client control metrics (command tower)
    inactive_clients: int = 0
    in_negotiation_clients: int = 0
    new_clients_this_month: int = 0
    active_contracts: int = 0
    open_service_orders: int = 0
    completed_service_orders: int = 0
    total_lots: int = 0
    available_lots: int = 0
    reserved_lots: int = 0
    sold_lots: int = 0


class FinancialOverview(BaseModel):
    """Financial summary for the admin dashboard."""

    total_receivable: Decimal = Decimal("0")
    total_received: Decimal = Decimal("0")
    total_overdue: Decimal = Decimal("0")
    overdue_count: int = 0
    # Collections coming due within the next 7 days.
    due_soon_amount: Decimal = Decimal("0")
    due_soon_count: int = 0

    # --- Current month -------------------------------------------------------
    # The totals above are lifetime figures, which say nothing about whether
    # this month is on track. These break the month down so the admin can see
    # the projection against what actually came in.

    # Everything falling due this month, whatever its status: the month's target.
    month_expected_amount: Decimal = Decimal("0")
    month_expected_count: int = 0
    # Cash actually settled this month, by paid_at -- includes payments of older
    # overdue installments, so it is the real inflow, not the month's target met.
    month_received_amount: Decimal = Decimal("0")
    month_received_count: int = 0
    # Due this month and still unpaid, split by whether the date has passed.
    month_open_amount: Decimal = Decimal("0")
    month_open_count: int = 0
    month_overdue_amount: Decimal = Decimal("0")
    month_overdue_count: int = 0
    # What is already scheduled for next month.
    next_month_expected_amount: Decimal = Decimal("0")
    next_month_expected_count: int = 0


class RevenueChartPoint(BaseModel):
    """Single data point for revenue chart."""

    month: str
    amount: Decimal


class ServiceChartPoint(BaseModel):
    """Service type popularity data point."""

    service_name: str
    count: int


class RecentActivity(BaseModel):
    """Generic recent activity entry (sourced from the audit trail)."""

    id: UUID
    type: str
    description: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Client Dashboard
# ---------------------------------------------------------------------------

class ClientSummary(BaseModel):
    """Summary data for the client portal."""

    total_lots: int = 0
    next_due_date: Optional[date] = None
    next_due_amount: Optional[Decimal] = None
    pending_invoices: int = 0
    overdue_invoices: int = 0


# ---------------------------------------------------------------------------
# Financial (admin)
# ---------------------------------------------------------------------------

class DefaulterInfo(BaseModel):
    """Info about a defaulting client."""

    client_id: UUID
    client_name: str
    overdue_months: int
    overdue_amount: Decimal


class DefaulterDetailResponse(BaseModel):
    """Detailed defaulter info for dashboard drill-down."""

    client_id: UUID
    client_name: str
    cpf_cnpj: str
    phone: str
    overdue_invoices: int
    overdue_amount: Decimal
    oldest_due_date: Optional[date] = None
    days_overdue: int = 0


class RevenueByService(BaseModel):
    """Revenue grouped by service type."""

    service_type_id: UUID
    service_name: str
    total_revenue: Decimal
    total_cost: Decimal
    order_count: int


class ActionQueueItem(BaseModel):
    """One thing waiting on a human decision, with where to go and act on it."""

    key: str
    label: str
    count: int = 0
    # Plain-language instruction: the dashboard is the control panel, so each
    # tile says what the number means and what to do about it.
    hint: str = ""
    href: str
    severity: str = "info"  # info | warning | critical


class ActionQueue(BaseModel):
    """Everything awaiting a decision, in one round-trip."""

    items: list[ActionQueueItem] = []
    total: int = 0


class BoletoStatusCount(BaseModel):
    status: str
    count: int = 0
    total_value: Decimal = Decimal("0")


class BillingPipeline(BaseModel):
    """Health of the billing chain, from invoice to registered boleto.

    `invoices_without_boleto` is the one that matters most: an installment with
    no boleto is never going to be paid, and it silently blocks the contract's
    cycle from ever being released.
    """

    invoices_without_boleto: int = 0
    invoices_without_boleto_amount: Decimal = Decimal("0")
    boletos_by_status: list[BoletoStatusCount] = []
    batches_in_progress: int = 0
    batches_failed_recently: int = 0
    last_sicredi_sync: Optional[datetime] = None
    sicredi_errors_24h: int = 0

