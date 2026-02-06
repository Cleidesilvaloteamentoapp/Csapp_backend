
"""Aggregate all v1 API routers into a single router."""

from fastapi import APIRouter

from app.api.v1 import auth, companies, webhooks
from app.api.v1.admin import clients as admin_clients
from app.api.v1.admin import dashboard as admin_dashboard
from app.api.v1.admin import financial as admin_financial
from app.api.v1.admin import lots as admin_lots
from app.api.v1.admin import services as admin_services
from app.api.v1.client import dashboard as client_dashboard
from app.api.v1.client import documents as client_documents
from app.api.v1.client import invoices as client_invoices
from app.api.v1.client import referrals as client_referrals
from app.api.v1.client import services as client_services

api_router = APIRouter()

# Auth (public + authenticated)
api_router.include_router(auth.router)

# Super admin
api_router.include_router(companies.router)

# Webhooks (public – validated internally)
api_router.include_router(webhooks.router)

# Company admin
api_router.include_router(admin_dashboard.router, prefix="/admin")
api_router.include_router(admin_clients.router, prefix="/admin")
api_router.include_router(admin_lots.router, prefix="/admin")
api_router.include_router(admin_lots.dev_router, prefix="/admin")
api_router.include_router(admin_financial.router, prefix="/admin")
api_router.include_router(admin_services.router, prefix="/admin")

# Client portal
api_router.include_router(client_dashboard.router, prefix="/client")
api_router.include_router(client_invoices.router, prefix="/client")
api_router.include_router(client_services.router, prefix="/client")
api_router.include_router(client_documents.router, prefix="/client")
api_router.include_router(client_referrals.router, prefix="/client")
