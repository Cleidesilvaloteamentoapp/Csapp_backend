
"""Sicredi webhook receiver endpoint.

Receives payment event notifications (e.g., LIQUIDACAO) from the Sicredi API.
Processes the event and updates the corresponding invoice status in the database.

SECURITY: This endpoint is public (called by Sicredi servers) but validates
the event structure. Sicredi does not yet support authentication on webhooks,
so we validate by matching nossoNumero against known invoices.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.enums import InvoiceStatus
from app.models.invoice import Invoice
from app.schemas.sicredi import WebhookEventResponse
from app.services.sicredi.schemas import WebhookEventPayload
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/sicredi", response_model=WebhookEventResponse)
async def sicredi_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Process Sicredi payment event notifications.

    Expected events:
    - LIQUIDACAO_PIX: Boleto paid via Pix QR Code
    - LIQUIDACAO_REDE: Boleto paid via Sicredi network
    - LIQUIDACAO_COMPE: Boleto paid via other institutions
    - LIQUIDACAO_CARTORIO: Boleto paid via cartório
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Parse the event payload
    try:
        event = WebhookEventPayload(**body)
    except Exception as exc:
        logger.warning("sicredi_webhook_parse_error", error=str(exc), body=body)
        raise HTTPException(status_code=400, detail=f"Invalid event payload: {exc}")

    nosso_numero = event.nossoNumero
    movimento = event.movimento

    if not nosso_numero or not movimento:
        logger.warning("sicredi_webhook_missing_fields", body=body)
        raise HTTPException(status_code=400, detail="Missing nossoNumero or movimento")

    logger.info(
        "sicredi_webhook_received",
        nosso_numero=nosso_numero,
        movimento=movimento,
        valor=str(event.valorLiquidacao) if event.valorLiquidacao else None,
        id_evento=event.idEventoWebhook,
    )

    # Look up the invoice by matching barcode or nossoNumero stored in the invoice
    # The nossoNumero is typically stored in the invoice's barcode or a dedicated field
    result = await db.execute(
        select(Invoice).where(Invoice.barcode == nosso_numero)
    )
    invoice = result.scalar_one_or_none()

    if not invoice:
        logger.warning("sicredi_webhook_invoice_not_found", nosso_numero=nosso_numero)
        return WebhookEventResponse(
            status="ignored",
            nosso_numero=nosso_numero,
            movimento=movimento,
            detail="Invoice not found for this nossoNumero",
        )

    # Process liquidation events
    if movimento and "LIQUIDACAO" in movimento.upper():
        invoice.status = InvoiceStatus.PAID
        invoice.paid_at = datetime.now(timezone.utc)
        await db.flush()

        logger.info(
            "sicredi_webhook_invoice_paid",
            invoice_id=str(invoice.id),
            nosso_numero=nosso_numero,
            valor=str(event.valorLiquidacao),
        )

        return WebhookEventResponse(
            status="processed",
            nosso_numero=nosso_numero,
            movimento=movimento,
            valor_liquidacao=event.valorLiquidacao,
            invoice_id=str(invoice.id),
        )

    logger.info("sicredi_webhook_unhandled_event", movimento=movimento)
    return WebhookEventResponse(
        status="ignored",
        nosso_numero=nosso_numero,
        movimento=movimento,
        detail=f"Unhandled event type: {movimento}",
    )
