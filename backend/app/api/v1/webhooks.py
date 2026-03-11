
"""Webhook endpoints for external integrations (Asaas)."""

import hmac
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.enums import InvoiceStatus
from app.models.invoice import Invoice
from app.utils.logging import get_logger

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
logger = get_logger(__name__)


def _verify_asaas_token(request: Request) -> None:
    """Validate Asaas webhook access token if configured."""
    if not settings.ASAAS_WEBHOOK_TOKEN:
        return
    token = request.headers.get("asaas-access-token", "")
    if not hmac.compare_digest(token, settings.ASAAS_WEBHOOK_TOKEN):
        logger.warning("asaas_webhook_auth_failed", ip=request.client.host if request.client else None)
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/asaas")
async def asaas_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Process Asaas payment events.

    Expected events:
    - PAYMENT_RECEIVED / PAYMENT_CONFIRMED → mark invoice as paid
    - PAYMENT_OVERDUE → mark invoice as overdue
    """
    _verify_asaas_token(request)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request")

    event = body.get("event")
    payment = body.get("payment", {})
    asaas_payment_id = payment.get("id")

    if not event or not asaas_payment_id:
        logger.warning("asaas_webhook_invalid")
        raise HTTPException(status_code=400, detail="Invalid payload")

    logger.info("asaas_webhook_received", event=event, payment_id=asaas_payment_id)

    result = await db.execute(
        select(Invoice).where(Invoice.asaas_payment_id == asaas_payment_id)
    )
    invoice = result.scalar_one_or_none()

    if not invoice:
        logger.warning("asaas_webhook_invoice_not_found", payment_id=asaas_payment_id)
        return {"status": "ignored", "reason": "invoice not found"}

    if event in ("PAYMENT_RECEIVED", "PAYMENT_CONFIRMED"):
        invoice.status = InvoiceStatus.PAID
        invoice.paid_at = datetime.now(timezone.utc)
        logger.info("invoice_marked_paid", invoice_id=str(invoice.id))

    elif event == "PAYMENT_OVERDUE":
        invoice.status = InvoiceStatus.OVERDUE
        logger.info("invoice_marked_overdue", invoice_id=str(invoice.id))

    else:
        logger.info("asaas_webhook_unhandled_event", event=event)
        return {"status": "ignored", "reason": f"unhandled event: {event}"}

    await db.flush()
    return {"status": "ok", "invoice_id": str(invoice.id), "new_status": invoice.status.value}
