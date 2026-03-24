
"""Abstract base class for WhatsApp providers."""

from abc import ABC, abstractmethod
from typing import Any, Optional

from app.services.whatsapp.schemas import ConnectionStatus, SendResult, TemplateInfo


class WhatsAppProviderBase(ABC):
    """Contract that every WhatsApp provider adapter must implement."""

    provider_name: str = "base"

    @abstractmethod
    async def send_text(self, to: str, body: str) -> SendResult:
        """Send a plain text message.

        Args:
            to: Phone number in international format (e.g. 5511999999999).
            body: Message text.
        """
        ...

    @abstractmethod
    async def send_template(
        self,
        to: str,
        template_name: str,
        language: str = "pt_BR",
        components: Optional[list[dict[str, Any]]] = None,
    ) -> SendResult:
        """Send a template-based message.

        Args:
            to: Phone number in international format.
            template_name: Pre-approved template name.
            language: Template language code.
            components: Template parameter components.
        """
        ...

    @abstractmethod
    async def check_connection(self) -> ConnectionStatus:
        """Check if the provider instance is connected and healthy."""
        ...

    # Optional: template management (only Meta implements these)
    async def list_templates(self, limit: int = 100) -> list[TemplateInfo]:
        """List available message templates. Default: not supported."""
        return []

    async def create_template(self, template_data: dict[str, Any]) -> TemplateInfo:
        """Create a new message template. Default: not supported."""
        raise NotImplementedError(f"{self.provider_name} does not support template management")

    async def get_template(self, template_name: str) -> Optional[TemplateInfo]:
        """Get template details by name. Default: not supported."""
        return None

    async def delete_template(self, template_name: str) -> bool:
        """Delete a template. Default: not supported."""
        raise NotImplementedError(f"{self.provider_name} does not support template management")
