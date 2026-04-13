from typing import Optional

"""Email notification service using Resend."""

import resend

from app.core.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _init_resend() -> None:
    """Configure the Resend SDK."""
    resend.api_key = settings.RESEND_API_KEY


async def send_email(
    to: str | list[str],
    subject: str,
    html: str,
    from_email: Optional[str] = None,
    from_name: Optional[str] = None,
) -> Optional[dict]:
    """Send an email via Resend.  Returns the API response dict or None on failure."""
    _init_resend()
    sender = f"{from_name or settings.SMTP_FROM_NAME} <{from_email or settings.SMTP_FROM_EMAIL}>"

    try:
        params = {
            "from_": sender,
            "to": to if isinstance(to, list) else [to],
            "subject": subject,
            "html": html,
        }
        response = resend.Emails.send(params)
        logger.info("email_sent", to=to, subject=subject)
        return response
    except Exception as exc:
        logger.error("email_send_failed", to=to, error=str(exc))
        return None


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------

async def send_welcome_email(to: str, client_name: str, company_name: str) -> None:
    """Send welcome email to a new client."""
    html = f"""
    <h2>Bem-vindo(a), {client_name}!</h2>
    <p>Sua conta foi criada com sucesso na <strong>{company_name}</strong>.</p>
    <p>Acesse o portal do cliente para visualizar seus lotes, boletos e documentos.</p>
    """
    await send_email(to=to, subject=f"Bem-vindo à {company_name}", html=html)


async def send_credentials_email(to: str, name: str, temp_password: str) -> None:
    """Send login credentials to a new client user."""
    html = f"""
    <h2>Suas credenciais de acesso</h2>
    <p>Olá, {name}. Seu acesso ao portal foi criado.</p>
    <p><strong>Email:</strong> {to}</p>
    <p><strong>Senha temporária:</strong> {temp_password}</p>
    <p>Recomendamos que altere sua senha no primeiro acesso.</p>
    """
    await send_email(to=to, subject="Suas credenciais de acesso", html=html)


async def send_invoice_email(to: str, name: str, due_date: str, amount: str, payment_url: str) -> None:
    """Notify client that a new boleto is available."""
    html = f"""
    <h2>Novo boleto disponível</h2>
    <p>Olá, {name}. Um novo boleto foi gerado para você.</p>
    <p><strong>Vencimento:</strong> {due_date}</p>
    <p><strong>Valor:</strong> R$ {amount}</p>
    <p><a href="{payment_url}">Clique aqui para pagar</a></p>
    """
    await send_email(to=to, subject="Novo boleto disponível", html=html)


async def send_payment_reminder(to: str, name: str, due_date: str, amount: str) -> None:
    """Send payment reminder."""
    html = f"""
    <h2>Lembrete de pagamento</h2>
    <p>Olá, {name}. Lembrete: seu boleto vence em <strong>{due_date}</strong>.</p>
    <p><strong>Valor:</strong> R$ {amount}</p>
    """
    await send_email(to=to, subject="Lembrete de pagamento", html=html)


async def send_overdue_alert(to: str, name: str, due_date: str, amount: str) -> None:
    """Send overdue payment alert."""
    html = f"""
    <h2>Alerta de atraso</h2>
    <p>Olá, {name}. Seu boleto com vencimento em <strong>{due_date}</strong> está em atraso.</p>
    <p><strong>Valor:</strong> R$ {amount}</p>
    <p>Por favor, regularize o pagamento o mais breve possível.</p>
    """
    await send_email(to=to, subject="Alerta: boleto em atraso", html=html)


async def send_rescission_alert(to: str, name: str, days_overdue: int) -> None:
    """Send rescission warning for long-term default."""
    html = f"""
    <h2>Alerta de possível rescisão</h2>
    <p>Olá, {name}. Identificamos que você está com <strong>{days_overdue} dias</strong> de atraso.</p>
    <p>Por favor, entre em contato conosco para regularizar sua situação e evitar a rescisão do contrato.</p>
    """
    await send_email(to=to, subject="URGENTE: Alerta de rescisão contratual", html=html)


async def send_service_order_update(to: str, name: str, order_id: str, new_status: str) -> None:
    """Notify client about a service order status change."""
    html = f"""
    <h2>Atualização de ordem de serviço</h2>
    <p>Olá, {name}. Sua ordem de serviço <strong>#{order_id[:8]}</strong> foi atualizada.</p>
    <p><strong>Novo status:</strong> {new_status}</p>
    """
    await send_email(to=to, subject="OS atualizada", html=html)


async def send_admin_alert(company_id: str, subject: str, message: str) -> None:
    """Send an alert email to all admins of a company.

    In production, this should look up admin emails from the database.
    For now, it sends to the configured SMTP_FROM_EMAIL as a fallback.
    """
    from sqlalchemy import select
    from app.core.database import async_session_factory
    from app.models.user import Profile
    from app.models.enums import UserRole

    admin_emails = []
    try:
        async with async_session_factory() as db:
            rows = await db.execute(
                select(Profile.email).where(
                    Profile.company_id == company_id,
                    Profile.role == UserRole.COMPANY_ADMIN,
                )
            )
            admin_emails = [r[0] for r in rows.all() if r[0]]
    except Exception as exc:
        logger.warning("admin_email_lookup_failed", company_id=company_id, error=str(exc))

    if not admin_emails:
        admin_emails = [settings.SMTP_FROM_EMAIL]

    html = f"""
    <h2>Alerta Administrativo</h2>
    <div style="padding: 16px; background: #fff3cd; border-left: 4px solid #ffc107; margin: 16px 0;">
        {message}
    </div>
    """
    await send_email(to=admin_emails, subject=f"[ADMIN] {subject}", html=html)


async def send_password_reset_email(to: str, reset_token: str) -> None:
    """Send password reset email with reset link."""
    # In production, this should use a frontend URL with the token as query param
    # For now, we'll include the token directly in the email
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"

    html = f"""
    <h2>Recuperação de Senha</h2>
    <p>Olá,</p>
    <p>Recebemos uma solicitação para redefinir a senha da sua conta.</p>
    <p>Clique no botão abaixo para criar uma nova senha:</p>
    <div style="text-align: center; margin: 24px 0;">
        <a href="{reset_url}" style="background: #007bff; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; display: inline-block;">
            Redefinir Senha
        </a>
    </div>
    <p>Ou copie e cole este link no navegador:</p>
    <p style="word-break: break-all; background: #f8f9fa; padding: 12px; border-radius: 4px;">
        {reset_url}
    </p>
    <p><strong>Este link expira em 15 minutos.</strong></p>
    <p>Se você não solicitou esta alteração, ignore este email.</p>
    <hr>
    <p style="font-size: 12px; color: #6c757d;">
        Este é um email automático. Por favor, não responda.
    </p>
    """
    await send_email(to=to, subject="Recuperação de Senha", html=html)
