
"""Aggregate all v1 API routers into a single router."""

from fastapi import APIRouter

from app.api.v1 import auth, companies, webhooks_sicredi
from app.api.v1.admin import clients as admin_clients
from app.api.v1.admin import contract_history as admin_contract_history
from app.api.v1.admin import dashboard as admin_dashboard
from app.api.v1.admin import financial as admin_financial
from app.api.v1.admin import lots as admin_lots
from app.api.v1.admin import renegotiations as admin_renegotiations
from app.api.v1.admin import reports as admin_reports
from app.api.v1.admin import rescissions as admin_rescissions
from app.api.v1.admin import segunda_via as admin_segunda_via
from app.api.v1.admin import services as admin_services
from app.api.v1.admin import sicredi as admin_sicredi
from app.api.v1.admin import boletos as admin_boletos
from app.api.v1.admin import documents as admin_documents
from app.api.v1.admin import service_requests as admin_service_requests
from app.api.v1.admin import economic_indices as admin_economic_indices
from app.api.v1.admin import cycle_approvals as admin_cycle_approvals
from app.api.v1.admin import transfers as admin_transfers
from app.api.v1.admin import early_payoff as admin_early_payoff
from app.api.v1.admin import bank_statements as admin_bank_statements
from app.api.v1.client import dashboard as client_dashboard
from app.api.v1.client import documents as client_documents
from app.api.v1.client import invoices as client_invoices
from app.api.v1.client import referrals as client_referrals
from app.api.v1.client import boletos as client_boletos
from app.api.v1.client import notifications as client_notifications
from app.api.v1.client import profile as client_profile
from app.api.v1.client import service_requests as client_service_requests
from app.api.v1.client import early_payoff as client_early_payoff
from app.api.v1.client import services as client_services

api_router = APIRouter()

# Auth (public + authenticated)
api_router.include_router(auth.router)

# Super admin
api_router.include_router(companies.router)

# Webhooks (public – validated internally)
api_router.include_router(webhooks_sicredi.router)

# Company admin
api_router.include_router(admin_dashboard.router, prefix="/admin")
api_router.include_router(admin_clients.router, prefix="/admin")
api_router.include_router(admin_lots.router, prefix="/admin")
api_router.include_router(admin_lots.dev_router, prefix="/admin")
api_router.include_router(admin_financial.router, prefix="/admin")
api_router.include_router(admin_services.router, prefix="/admin")
api_router.include_router(admin_sicredi.router, prefix="/admin")
api_router.include_router(admin_boletos.router, prefix="/admin")
api_router.include_router(admin_contract_history.router, prefix="/admin")
api_router.include_router(admin_renegotiations.router, prefix="/admin")
api_router.include_router(admin_rescissions.router, prefix="/admin")
api_router.include_router(admin_segunda_via.router, prefix="/admin")
api_router.include_router(admin_reports.router, prefix="/admin")
api_router.include_router(admin_documents.router, prefix="/admin")
api_router.include_router(admin_service_requests.router, prefix="/admin")
api_router.include_router(admin_economic_indices.router, prefix="/admin")
api_router.include_router(admin_cycle_approvals.router, prefix="/admin")
api_router.include_router(admin_transfers.router, prefix="/admin")
api_router.include_router(admin_early_payoff.router, prefix="/admin")
api_router.include_router(admin_bank_statements.router, prefix="/admin")

# Client portal
api_router.include_router(client_dashboard.router, prefix="/client")
api_router.include_router(client_invoices.router, prefix="/client")
api_router.include_router(client_services.router, prefix="/client")
api_router.include_router(client_documents.router, prefix="/client")
api_router.include_router(client_boletos.router, prefix="/client")
api_router.include_router(client_referrals.router, prefix="/client")
api_router.include_router(client_profile.router, prefix="/client")
api_router.include_router(client_service_requests.router, prefix="/client")
api_router.include_router(client_notifications.router, prefix="/client")
api_router.include_router(client_early_payoff.router, prefix="/client")
