from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal
from datetime import date


class AdminDashboardStats(BaseModel):
    total_clients: int
    active_clients: int
    defaulter_clients: int
    total_lots: int
    available_lots: int
    sold_lots: int
    open_service_orders: int
    completed_service_orders: int


class DefaulterInfo(BaseModel):
    client_id: str
    client_name: str
    cpf_cnpj: str
    phone: str
    overdue_amount: Decimal
    overdue_invoices_count: int
    oldest_overdue_date: date


class AdminFinancialDashboard(BaseModel):
    total_receivables: Decimal
    total_received: Decimal
    total_overdue: Decimal
    defaulters: List[DefaulterInfo]
    revenue_from_services: Decimal
    service_costs: Decimal
    service_profit: Decimal


class ClientDashboardResponse(BaseModel):
    client_name: str
    total_lots: int
    lots: List[dict]
    pending_invoices: int
    total_pending_amount: Decimal
    next_due_date: Optional[date] = None
    open_service_orders: int
    recent_notifications: List[dict]
