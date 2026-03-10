
"""Audit logging utility for recording sensitive operations."""

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Tables that always require audit logging
AUDITED_TABLES = frozenset({
    "clients",
    "client_lots",
    "invoices",
    "boletos",
    "batch_operations",
    "renegotiations",
    "rescissions",
    "contract_history",
    "sicredi_credentials",
    "profiles",
})


async def log_audit(
    db: AsyncSession,
    *,
    user_id: Optional[UUID],
    company_id: Optional[UUID],
    table_name: str,
    operation: str,
    resource_id: Optional[str] = None,
    detail: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Record an audit log entry for a sensitive operation.

    This should be called from endpoints that modify sensitive data.
    """
    if table_name not in AUDITED_TABLES:
        return

    entry = AuditLog(
        user_id=user_id,
        company_id=company_id,
        table_name=table_name,
        operation=operation,
        resource_id=resource_id,
        detail=detail,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(entry)
    await db.flush()
    logger.info(
        "audit_logged",
        table=table_name,
        operation=operation,
        resource_id=resource_id,
        user_id=str(user_id) if user_id else None,
    )
