
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

from app.core.config import settings
from app.core.database import get_db
from app.models.enums import InvoiceStatus, BoletoStatus
from app.models.invoice import Invoice
from app.models.boleto import Boleto
from app.schemas.sicredi import WebhookEventResponse
from app.services.sicredi.schemas import WebhookEventPayload
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def _verify_sicredi_origin(request: Request) -> None:
    """Validate Sicredi webhook origin IP if whitelist is configured."""
    if not settings.WEBHOOK_IP_WHITELIST:
        return
    client_ip = request.client.host if request.client else None
    if client_ip not in settings.WEBHOOK_IP_WHITELIST:
        logger.warning("sicredi_webhook_ip_rejected", ip=client_ip)
        raise HTTPException(status_code=403, detail="Forbidden")


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
    _verify_sicredi_origin(request)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request")

    # Parse the event payload
    try:
        event = WebhookEventPayload(**body)
    except Exception as exc:
        logger.warning("sicredi_webhook_parse_error", error=str(exc))
        raise HTTPException(status_code=400, detail="Invalid event payload")

    nosso_numero = event.nossoNumero
    movimento = event.movimento

    if not nosso_numero or not movimento:
        logger.warning("sicredi_webhook_missing_fields")
        raise HTTPException(status_code=400, detail="Invalid payload")

    logger.info(
        "sicredi_webhook_received",
        nosso_numero=nosso_numero,
        movimento=movimento,
        valor=str(event.valorLiquidacao) if event.valorLiquidacao else None,
        id_evento=event.idEventoWebhook,
    )

    # Look up the boleto by nossoNumero
    result_boleto = await db.execute(
        select(Boleto).where(Boleto.nosso_numero == nosso_numero)
    )
    boleto = result_boleto.scalar_one_or_none()
    
    # Also look up invoice by matching barcode (legacy support)
    result_invoice = await db.execute(
        select(Invoice).where(Invoice.barcode == nosso_numero)
    )
    invoice = result_invoice.scalar_one_or_none()

    if not boleto and not invoice:
        logger.warning("sicredi_webhook_boleto_not_found", nosso_numero=nosso_numero)
        return WebhookEventResponse(
            status="ignored",
            nosso_numero=nosso_numero,
            movimento=movimento,
            detail="Boleto or invoice not found for this nossoNumero",
        )

    # Process liquidation events
    if movimento and "LIQUIDACAO" in movimento.upper():
        # Update boleto status
        if boleto:
            boleto.status = BoletoStatus.LIQUIDADO
            boleto.data_liquidacao = datetime.now(timezone.utc).date()
            boleto.valor_liquidacao = event.valorLiquidacao
            await db.flush()
            
            logger.info(
                "sicredi_webhook_boleto_paid",
                boleto_id=str(boleto.id),
                nosso_numero=nosso_numero,
                valor=str(event.valorLiquidacao),
            )
            
            # If boleto is linked to an invoice, update invoice too
            if boleto.invoice_id:
                result_linked_invoice = await db.execute(
                    select(Invoice).where(Invoice.id == boleto.invoice_id)
                )
                linked_invoice = result_linked_invoice.scalar_one_or_none()
                if linked_invoice:
                    linked_invoice.status = InvoiceStatus.PAID
                    linked_invoice.paid_at = datetime.now(timezone.utc)
                    await db.flush()
        
        # Update invoice status (legacy support)
        if invoice:
            invoice.status = InvoiceStatus.PAID
            invoice.paid_at = datetime.now(timezone.utc)
            await db.flush()

            logger.info(
                "sicredi_webhook_invoice_paid",
                invoice_id=str(invoice.id),
                nosso_numero=nosso_numero,
                valor=str(event.valorLiquidacao),
            )
        
        await db.commit()

        return WebhookEventResponse(
            status="processed",
            nosso_numero=nosso_numero,
            movimento=movimento,
            valor_liquidacao=event.valorLiquidacao,
            invoice_id=str(invoice.id) if invoice else None,
        )

    logger.info("sicredi_webhook_unhandled_event", movimento=movimento)
    return WebhookEventResponse(
        status="ignored",
        nosso_numero=nosso_numero,
        movimento=movimento,
        detail=f"Unhandled event type: {movimento}",
    )
