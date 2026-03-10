
"""Notification service – create in-app notifications for users."""

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import NotificationType
from app.models.notification import Notification
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def create_notification(
    db: AsyncSession,
    *,
    company_id: UUID,
    user_id: UUID,
    title: str,
    message: str,
    notification_type: NotificationType = NotificationType.GERAL,
    data: Optional[dict] = None,
) -> Notification:
    """Create an in-app notification for a specific user."""
    notif = Notification(
        company_id=company_id,
        user_id=user_id,
        title=title,
        message=message,
        type=notification_type,
        is_read=False,
        data=data or {},
    )
    db.add(notif)
    await db.flush()
    logger.info(
        "notification_created",
        user_id=str(user_id),
        type=notification_type.value,
        title=title,
    )
    return notif


async def notify_document_reviewed(
    db: AsyncSession,
    *,
    company_id: UUID,
    user_id: UUID,
    document_type: str,
    status: str,
) -> Notification:
    """Notify client that their document was reviewed."""
    if status == "APPROVED":
        n_type = NotificationType.DOCUMENTO_APROVADO
        title = "Documento aprovado"
        message = f"Seu documento ({document_type}) foi aprovado."
    else:
        n_type = NotificationType.DOCUMENTO_REJEITADO
        title = "Documento rejeitado"
        message = f"Seu documento ({document_type}) foi rejeitado. Verifique os detalhes e envie novamente."

    return await create_notification(
        db,
        company_id=company_id,
        user_id=user_id,
        title=title,
        message=message,
        notification_type=n_type,
        data={"document_type": document_type, "review_status": status},
    )


async def notify_service_request_updated(
    db: AsyncSession,
    *,
    company_id: UUID,
    user_id: UUID,
    ticket_number: str,
    new_status: str,
) -> Notification:
    """Notify client about a service request status change."""
    return await create_notification(
        db,
        company_id=company_id,
        user_id=user_id,
        title="Solicitação atualizada",
        message=f"Sua solicitação {ticket_number} foi atualizada para: {new_status}.",
        notification_type=NotificationType.SOLICITACAO_ATUALIZADA,
        data={"ticket_number": ticket_number, "new_status": new_status},
    )


async def notify_boleto_emitido(
    db: AsyncSession,
    *,
    company_id: UUID,
    user_id: UUID,
    nosso_numero: str,
    valor: str,
    data_vencimento: str,
) -> Notification:
    """Notify client that a new boleto was issued."""
    return await create_notification(
        db,
        company_id=company_id,
        user_id=user_id,
        title="Novo boleto emitido",
        message=f"Boleto {nosso_numero} no valor de R$ {valor} com vencimento em {data_vencimento}.",
        notification_type=NotificationType.BOLETO_EMITIDO,
        data={"nosso_numero": nosso_numero, "valor": valor, "data_vencimento": data_vencimento},
    )


async def notify_pagamento_confirmado(
    db: AsyncSession,
    *,
    company_id: UUID,
    user_id: UUID,
    nosso_numero: str,
    valor: str,
) -> Notification:
    """Notify client that a payment was confirmed."""
    return await create_notification(
        db,
        company_id=company_id,
        user_id=user_id,
        title="Pagamento confirmado",
        message=f"Pagamento do boleto {nosso_numero} no valor de R$ {valor} foi confirmado.",
        notification_type=NotificationType.PAGAMENTO_CONFIRMADO,
        data={"nosso_numero": nosso_numero, "valor": valor},
    )
