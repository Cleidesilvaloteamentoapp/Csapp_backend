
"""Sicredi Cobrança API integration module.

Reusable module for managing boletos (bank slips) via Sicredi's REST API.
Supports: OAuth2 authentication, boleto CRUD, PDF generation, and webhook management.

Usage:
    from app.services.sicredi import SicrediClient, SicrediCredentials

    creds = SicrediCredentials(
        x_api_key="...",
        username="...",
        password="...",
        cooperativa="...",
        posto="...",
        codigo_beneficiario="...",
    )
    client = SicrediClient(credentials=creds)
    boleto = await client.boletos.criar(payload)
"""

from app.services.sicredi.auth import SicrediAuth
from app.services.sicredi.boletos import SicrediBoletos
from app.services.sicredi.client import SicrediClient
from app.services.sicredi.config import SicrediCredentials, SicrediEnvironment
from app.services.sicredi.exceptions import (
    SicrediAuthError,
    SicrediError,
    SicrediNotFoundError,
    SicrediRateLimitError,
    SicrediValidationError,
)
from app.services.sicredi.webhooks import SicrediWebhooks

__all__ = [
    "SicrediAuth",
    "SicrediBoletos",
    "SicrediClient",
    "SicrediCredentials",
    "SicrediEnvironment",
    "SicrediWebhooks",
    "SicrediError",
    "SicrediAuthError",
    "SicrediValidationError",
    "SicrediNotFoundError",
    "SicrediRateLimitError",
]
