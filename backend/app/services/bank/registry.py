
"""Bank provider registry — maps bank codes to provider instances."""

from typing import Optional
from uuid import UUID

from app.services.bank.base import BankProvider
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Global registry: bank_code -> provider class
_PROVIDERS: dict[str, type[BankProvider]] = {}

# Per-company provider instances (company_id -> provider instance)
_INSTANCES: dict[UUID, BankProvider] = {}


def register_bank_provider(bank_code: str, provider_class: type[BankProvider]) -> None:
    """Register a bank provider class by its FEBRABAN code."""
    _PROVIDERS[bank_code] = provider_class
    logger.info("bank_provider_registered", bank_code=bank_code, provider=provider_class.__name__)


def get_bank_provider(bank_code: str, company_id: Optional[UUID] = None) -> type[BankProvider]:
    """Retrieve a registered bank provider class by FEBRABAN code.

    Args:
        bank_code: FEBRABAN bank code (e.g. '748' for Sicredi)
        company_id: Optional company_id for future per-company caching

    Returns:
        The provider class (not an instance — caller must instantiate).

    Raises:
        ValueError: If no provider is registered for the given bank code.
    """
    if bank_code not in _PROVIDERS:
        raise ValueError(
            f"No bank provider registered for code '{bank_code}'. "
            f"Available: {list(_PROVIDERS.keys())}"
        )
    return _PROVIDERS[bank_code]


def list_registered_providers() -> dict[str, str]:
    """Return a dict of {bank_code: class_name} for all registered providers."""
    return {code: cls.__name__ for code, cls in _PROVIDERS.items()}
