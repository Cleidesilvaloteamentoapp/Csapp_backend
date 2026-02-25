
"""Sicredi API configuration and credentials model."""

import enum
from dataclasses import dataclass, field
from typing import Optional


class SicrediEnvironment(str, enum.Enum):
    """API environment selector."""

    SANDBOX = "sandbox"
    PRODUCTION = "production"


# Base URLs per environment
_BASE_URLS = {
    SicrediEnvironment.SANDBOX: "https://api-parceiro.sicredi.com.br/sb",
    SicrediEnvironment.PRODUCTION: "https://api-parceiro.sicredi.com.br",
}

# Auth URLs per environment
_AUTH_URLS = {
    SicrediEnvironment.SANDBOX: "https://api-parceiro.sicredi.com.br/sb/auth/openapi/token",
    SicrediEnvironment.PRODUCTION: "https://api-parceiro.sicredi.com.br/auth/openapi/token",
}


@dataclass(frozen=False)
class SicrediCredentials:
    """Credentials required to authenticate with the Sicredi Cobrança API.

    Attributes:
        x_api_key: UUID token from the Sicredi developer portal.
        username: Beneficiário code + Cooperativa code (e.g. "123456789").
        password: Access code generated via Internet Banking.
        cooperativa: Cooperativa code of the beneficiary.
        posto: Agência/posto code of the beneficiary.
        codigo_beneficiario: Convenio code for billing.
        environment: sandbox or production.
    """

    x_api_key: str
    username: str
    password: str
    cooperativa: str
    posto: str
    codigo_beneficiario: str
    environment: SicrediEnvironment = SicrediEnvironment.PRODUCTION

    # Token cache (managed by SicrediAuth)
    _access_token: Optional[str] = field(default=None, repr=False)
    _refresh_token: Optional[str] = field(default=None, repr=False)
    _token_expires_at: Optional[float] = field(default=None, repr=False)
    _refresh_expires_at: Optional[float] = field(default=None, repr=False)

    @property
    def base_url(self) -> str:
        """Return the base API URL for the current environment."""
        return _BASE_URLS[self.environment]

    @property
    def auth_url(self) -> str:
        """Return the auth URL for the current environment."""
        return _AUTH_URLS[self.environment]

    @property
    def boleto_base_url(self) -> str:
        """Return the boleto API base URL."""
        return f"{self.base_url}/cobranca/boleto/v1"


# Default HTTP timeout in seconds
HTTP_TIMEOUT = 30

# Token safety margin: refresh N seconds before actual expiration
TOKEN_REFRESH_MARGIN_SECONDS = 30
