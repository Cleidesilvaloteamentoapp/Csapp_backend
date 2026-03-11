from typing import Optional

"""Multi-tenant context middleware and helpers.

Every request carries a tenant context (company_id) derived from the
authenticated user's profile.  The middleware injects this into a
context variable so that service-layer code can read it without passing
it through every function signature.
"""

from contextvars import ContextVar
from uuid import UUID

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.utils.logging import get_logger

logger = get_logger(__name__)

# Context variables accessible anywhere in the async call chain.
current_company_id: ContextVar[Optional[UUID]] = ContextVar("current_company_id", default=None)
current_user_id: ContextVar[Optional[UUID]] = ContextVar("current_user_id", default=None)
current_user_role: ContextVar[Optional[str]] = ContextVar("current_user_role", default=None)


class TenantMiddleware(BaseHTTPMiddleware):
    """Extracts tenant context from the request state (set by auth deps)
    and stores it in context variables for downstream use."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Auth dependency sets these on request.state before route runs.
        # If not present (e.g. unauthenticated routes), defaults remain None.
        company_id = getattr(request.state, "company_id", None)
        user_id = getattr(request.state, "user_id", None)
        user_role = getattr(request.state, "user_role", None)

        token_company = current_company_id.set(company_id)
        token_user = current_user_id.set(user_id)
        token_role = current_user_role.set(user_role)

        try:
            response = await call_next(request)
        finally:
            current_company_id.reset(token_company)
            current_user_id.reset(token_user)
            current_user_role.reset(token_role)

        return response


def get_tenant_filter(company_id_column, *, allow_super_admin: bool = True):
    """Return an SQLAlchemy filter clause for multi-tenant isolation.

    If the current user is super_admin and *allow_super_admin* is True,
    no filter is applied (returns True – all rows).  Otherwise it
    filters by the current tenant.
    """
    from sqlalchemy import true as sa_true

    role = current_user_role.get()
    if allow_super_admin and role == "SUPER_ADMIN":
        return sa_true()

    cid = current_company_id.get()
    if cid is None:
        # Safety net – should never happen on authenticated endpoints
        from app.utils.exceptions import TenantIsolationError
        raise TenantIsolationError("Tenant context not set")
    return company_id_column == cid
