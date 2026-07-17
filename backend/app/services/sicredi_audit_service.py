
"""Service for logging Sicredi interactions to the immutable audit trail."""

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sicredi_event import SicrediEvent
from app.utils.logging import get_logger

logger = get_logger(__name__)

DIRECTION_INBOUND = "INBOUND"
DIRECTION_OUTBOUND = "OUTBOUND"


def _sanitize(payload: object) -> Optional[dict]:
    """Coerce arbitrary payloads into a JSON-serializable dict for storage."""
    if payload is None:
        return None
    if isinstance(payload, dict):
        return payload
    if hasattr(payload, "model_dump"):
        try:
            return payload.model_dump(mode="json")
        except Exception:
            return {"repr": str(payload)}
    return {"value": str(payload)}


async def log_sicredi_event(
    db: AsyncSession,
    *,
    direction: str,
    event_type: str,
    company_id: Optional[UUID] = None,
    nosso_numero: Optional[str] = None,
    boleto_id: Optional[UUID] = None,
    invoice_id: Optional[UUID] = None,
    http_status: Optional[int] = None,
    success: Optional[bool] = None,
    payload: object = None,
    webhook_event_id: Optional[str] = None,
) -> Optional[SicrediEvent]:
    """Record one Sicredi request/response. Best-effort: never raises.

    The caller is responsible for committing the surrounding transaction.
    """
    try:
        event = SicrediEvent(
            company_id=company_id,
            direction=direction,
            event_type=event_type,
            nosso_numero=nosso_numero,
            boleto_id=boleto_id,
            invoice_id=invoice_id,
            http_status=http_status,
            success=success,
            payload=_sanitize(payload),
            webhook_event_id=webhook_event_id,
        )
        db.add(event)
        await db.flush()
        return event
    except Exception as exc:  # pragma: no cover - auditing must not break flows
        logger.warning("sicredi_event_log_failed", event_type=event_type, error=str(exc))
        return None
