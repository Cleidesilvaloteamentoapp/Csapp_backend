
"""WhatsApp multi-provider module.

Provides abstract base + concrete adapters for UAZAPI and Meta Cloud API.
"""

from app.services.whatsapp.base import WhatsAppProviderBase  # noqa: F401
from app.services.whatsapp.schemas import ConnectionStatus, SendResult, TemplateInfo  # noqa: F401
from app.services.whatsapp.uazapi import UazapiProvider  # noqa: F401
from app.services.whatsapp.meta import MetaCloudProvider  # noqa: F401
