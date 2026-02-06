
"""WhatsApp notification service (Twilio adapter)."""

from app.core.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def send_whatsapp_message(to: str, body: str) -> bool:
    """Send a WhatsApp message via Twilio.

    Returns True on success, False on failure.
    """
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        logger.warning("whatsapp_not_configured")
        return False

    try:
        from twilio.rest import Client as TwilioClient

        client = TwilioClient(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=body,
            from_=f"whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}",
            to=f"whatsapp:{to}",
        )
        logger.info("whatsapp_sent", sid=message.sid, to=to)
        return True
    except Exception as exc:
        logger.error("whatsapp_failed", to=to, error=str(exc))
        return False


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------

async def notify_invoice_due(to: str, name: str, due_date: str, amount: str) -> bool:
    """Notify about upcoming invoice."""
    body = (
        f"Olá, {name}! Lembrete: seu boleto de R$ {amount} "
        f"vence em {due_date}. Acesse o portal para mais detalhes."
    )
    return await send_whatsapp_message(to, body)


async def notify_invoice_overdue(to: str, name: str, due_date: str, amount: str) -> bool:
    """Notify about overdue invoice."""
    body = (
        f"Olá, {name}. Seu boleto de R$ {amount} com vencimento em "
        f"{due_date} está em atraso. Regularize o quanto antes."
    )
    return await send_whatsapp_message(to, body)


async def notify_service_order(to: str, name: str, status: str) -> bool:
    """Notify about service order update."""
    body = f"Olá, {name}. Sua ordem de serviço foi atualizada para: {status}."
    return await send_whatsapp_message(to, body)
