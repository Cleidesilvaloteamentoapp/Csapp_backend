
"""WhatsApp notification service – multi-provider dispatcher.

Routes messages through the company's configured WhatsApp provider
(UAZAPI or Meta Cloud API) loaded from the database.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WhatsAppProviderType
from app.services.whatsapp_credential_service import get_provider
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def send_whatsapp_message(
    to: str,
    body: str,
    *,
    db: AsyncSession,
    company_id: UUID,
    provider_type: Optional[WhatsAppProviderType] = None,
) -> bool:
    """Send a WhatsApp text message via the company's configured provider.

    Returns True on success, False on failure.
    """
    try:
        provider = await get_provider(db, company_id, provider_type)
        result = await provider.send_text(to=to, body=body)
        if result.success:
            logger.info("whatsapp_sent", to=to, provider=result.provider)
        else:
            logger.warning("whatsapp_send_failed", to=to, provider=result.provider, error=result.error)
        return result.success
    except Exception as exc:
        logger.warning("whatsapp_not_configured_or_failed", company_id=str(company_id), error=str(exc))
        return False


async def send_whatsapp_template(
    to: str,
    template_name: str,
    *,
    db: AsyncSession,
    company_id: UUID,
    language: str = "pt_BR",
    components: Optional[list[dict]] = None,
    provider_type: Optional[WhatsAppProviderType] = None,
) -> bool:
    """Send a WhatsApp template message (Meta Cloud API).

    Returns True on success, False on failure.
    """
    try:
        provider = await get_provider(db, company_id, provider_type)
        result = await provider.send_template(
            to=to,
            template_name=template_name,
            language=language,
            components=components,
        )
        if result.success:
            logger.info("whatsapp_template_sent", to=to, template=template_name, provider=result.provider)
        else:
            logger.warning("whatsapp_template_failed", to=to, template=template_name, error=result.error)
        return result.success
    except Exception as exc:
        logger.warning("whatsapp_template_not_configured", company_id=str(company_id), error=str(exc))
        return False


# ---------------------------------------------------------------------------
# Template helpers (notification shortcuts)
# ---------------------------------------------------------------------------

async def notify_invoice_due(
    to: str, name: str, due_date: str, amount: str,
    *, db: AsyncSession, company_id: UUID,
) -> bool:
    """Notify about upcoming invoice."""
    body = (
        f"Olá, {name}! Lembrete: seu boleto de R$ {amount} "
        f"vence em {due_date}. Acesse o portal para mais detalhes."
    )
    return await send_whatsapp_message(to, body, db=db, company_id=company_id)


async def notify_invoice_overdue(
    to: str, name: str, due_date: str, amount: str,
    *, db: AsyncSession, company_id: UUID,
) -> bool:
    """Notify about overdue invoice."""
    body = (
        f"Olá, {name}. Seu boleto de R$ {amount} com vencimento em "
        f"{due_date} está em atraso. Regularize o quanto antes."
    )
    return await send_whatsapp_message(to, body, db=db, company_id=company_id)


async def notify_service_order(
    to: str, name: str, status: str,
    *, db: AsyncSession, company_id: UUID,
) -> bool:
    """Notify about service order update."""
    body = f"Olá, {name}. Sua ordem de serviço foi atualizada para: {status}."
    return await send_whatsapp_message(to, body, db=db, company_id=company_id)
