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
    open_service_orders: int = 0
    completed_service_orders: int = 0
    total_lots: int = 0
    available_lots: int = 0
    sold_lots: int = 0


class FinancialOverview(BaseModel):
    """Financial summary for the admin dashboard."""

    total_receivable: Decimal = Decimal("0")
    total_received: Decimal = Decimal("0")
    total_overdue: Decimal = Decimal("0")
    overdue_count: int = 0


class RevenueChartPoint(BaseModel):
    """Single data point for revenue chart."""

    month: str
    amount: Decimal


class ServiceChartPoint(BaseModel):
    """Service type popularity data point."""

    service_name: str
    count: int


class RecentActivity(BaseModel):
    """Generic recent activity entry."""

    id: UUID
    action: str
    description: str
    timestamp: datetime


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
