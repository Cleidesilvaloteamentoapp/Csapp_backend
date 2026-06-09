
"""WhatsApp notification service – multi-provider dispatcher.

Routes messages through the company's configured WhatsApp provider
(UAZAPI or Meta Cloud API) loaded from the database.

For Meta Cloud API, scheduled/outbound notifications sent outside the 24-hour
conversation window must use approved templates (send_template).  UAZAPI
supports free-form text at any time (send_text).  The helpers in this module
detect the active provider type and choose the right method automatically.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WhatsAppProviderType
from app.models.whatsapp_credential import WhatsAppCredential
from app.services.whatsapp_credential_service import get_provider
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def _get_default_provider_type(db: AsyncSession, company_id: UUID) -> Optional[WhatsAppProviderType]:
    """Return the provider type of the default (or only active) credential, or None."""
    result = await db.execute(
        select(WhatsAppCredential).where(
            WhatsAppCredential.company_id == company_id,
            WhatsAppCredential.is_active == True,
        ).order_by(WhatsAppCredential.is_default.desc())
    )
    cred = result.scalars().first()
    if cred is None:
        return None
    return WhatsAppProviderType(cred.provider) if isinstance(cred.provider, str) else cred.provider


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

async def notify_new_boleto(
    to: str,
    name: str,
    due_date: str,
    amount: str,
    linha_digitavel: str,
    portal_url: str,
    *,
    db: AsyncSession,
    company_id: UUID,
) -> bool:
    """Notify client about a newly generated boleto (link portal + linha digitável)."""
    provider_type = await _get_default_provider_type(db, company_id)

    if provider_type == WhatsAppProviderType.META:
        return await send_whatsapp_template(
            to=to,
            template_name="boleto_novo",
            db=db,
            company_id=company_id,
            components=[
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": name},
                        {"type": "text", "text": f"R$ {amount}"},
                        {"type": "text", "text": due_date},
                        {"type": "text", "text": linha_digitavel},
                        {"type": "text", "text": portal_url},
                    ],
                }
            ],
        )

    body = (
        f"Olá, {name}! Um novo boleto foi gerado para você.\n"
        f"Valor: R$ {amount} | Vencimento: {due_date}\n"
        f"Linha digitável: {linha_digitavel}\n"
        f"Acesse o portal: {portal_url}"
    )
    return await send_whatsapp_message(to, body, db=db, company_id=company_id)


async def notify_invoice_due(
    to: str, name: str, due_date: str, amount: str,
    *, db: AsyncSession, company_id: UUID,
) -> bool:
    """Notify about upcoming invoice."""
    provider_type = await _get_default_provider_type(db, company_id)

    if provider_type == WhatsAppProviderType.META:
        return await send_whatsapp_template(
            to=to,
            template_name="lembrete_vencimento",
            db=db,
            company_id=company_id,
            components=[
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": name},
                        {"type": "text", "text": f"R$ {amount}"},
                        {"type": "text", "text": due_date},
                    ],
                }
            ],
        )

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
    provider_type = await _get_default_provider_type(db, company_id)

    if provider_type == WhatsAppProviderType.META:
        return await send_whatsapp_template(
            to=to,
            template_name="aviso_atraso",
            db=db,
            company_id=company_id,
            components=[
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": name},
                        {"type": "text", "text": f"R$ {amount}"},
                        {"type": "text", "text": due_date},
                    ],
                }
            ],
        )

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
    provider_type = await _get_default_provider_type(db, company_id)

    if provider_type == WhatsAppProviderType.META:
        return await send_whatsapp_template(
            to=to,
            template_name="aviso_servico",
            db=db,
            company_id=company_id,
            components=[
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": name},
                        {"type": "text", "text": status},
                    ],
                }
            ],
        )

    body = f"Olá, {name}. Sua ordem de serviço foi atualizada para: {status}."
    return await send_whatsapp_message(to, body, db=db, company_id=company_id)
