import httpx
from typing import Optional
from app.core.config import get_settings


class EmailService:
    """Service for sending emails"""
    
    def __init__(self):
        settings = get_settings()
        self.api_key = settings.EMAIL_PROVIDER_API_KEY
        self.from_address = settings.EMAIL_FROM_ADDRESS
    
    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None
    ) -> bool:
        """
        Send an email
        Implementation depends on the email provider (SendGrid, AWS SES, etc.)
        """
        if not self.api_key:
            return False
        
        # TODO: Implement actual email sending based on provider
        # This is a placeholder for the email sending logic
        print(f"Sending email to {to}: {subject}")
        return True
    
    async def send_invoice_notification(
        self,
        to: str,
        client_name: str,
        invoice_amount: float,
        due_date: str,
        payment_url: str
    ) -> bool:
        """Send invoice notification email"""
        subject = f"Novo Boleto Disponível - Vencimento {due_date}"
        body = f"""
        Olá {client_name},
        
        Um novo boleto foi gerado para você.
        
        Valor: R$ {invoice_amount:.2f}
        Vencimento: {due_date}
        
        Acesse o link abaixo para visualizar e pagar:
        {payment_url}
        
        Atenciosamente,
        Equipe de Cobrança
        """
        
        return await self.send_email(to, subject, body)
    
    async def send_overdue_notification(
        self,
        to: str,
        client_name: str,
        overdue_amount: float,
        days_overdue: int
    ) -> bool:
        """Send overdue payment notification"""
        subject = f"Aviso de Pagamento em Atraso"
        body = f"""
        Olá {client_name},
        
        Identificamos que você possui pagamentos em atraso.
        
        Valor em atraso: R$ {overdue_amount:.2f}
        Dias em atraso: {days_overdue}
        
        Por favor, regularize sua situação o mais breve possível.
        
        Em caso de dúvidas, entre em contato conosco.
        
        Atenciosamente,
        Equipe de Cobrança
        """
        
        return await self.send_email(to, subject, body)


class WhatsAppService:
    """Service for sending WhatsApp messages"""
    
    def __init__(self):
        settings = get_settings()
        self.api_key = settings.WHATSAPP_API_KEY
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        self.base_url = f"https://graph.facebook.com/v17.0/{self.phone_number_id}/messages"
    
    async def send_message(self, to: str, message: str) -> bool:
        """
        Send WhatsApp message using Meta Business API
        """
        if not self.api_key or not self.phone_number_id:
            return False
        
        phone = to.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
        
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "text",
            "text": {"body": message}
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.base_url,
                    json=payload,
                    headers=headers,
                    timeout=30.0
                )
                response.raise_for_status()
                return True
        except Exception as e:
            print(f"WhatsApp send error: {e}")
            return False
    
    async def send_service_order_update(
        self,
        to: str,
        client_name: str,
        order_id: str,
        status: str,
        notes: Optional[str] = None
    ) -> bool:
        """Send service order status update via WhatsApp"""
        status_messages = {
            "approved": "foi aprovada",
            "in_progress": "está em andamento",
            "completed": "foi concluída",
            "cancelled": "foi cancelada"
        }
        
        status_text = status_messages.get(status, status)
        
        message = f"""
Olá {client_name}!

Sua ordem de serviço #{order_id[:8]} {status_text}.
"""
        
        if notes:
            message += f"\nObservações: {notes}"
        
        message += "\n\nEm caso de dúvidas, entre em contato."
        
        return await self.send_message(to, message)


def get_email_service() -> EmailService:
    return EmailService()


def get_whatsapp_service() -> WhatsAppService:
    return WhatsAppService()
