
"""Multi-bank abstraction layer.

Provides a uniform interface for boleto operations regardless of the
underlying bank integration (Sicredi, Itaú, Bradesco, etc.).
"""

from app.services.bank.base import BankProvider, BoletoResult
from app.services.bank.registry import get_bank_provider, register_bank_provider

__all__ = [
    "BankProvider",
    "BoletoResult",
    "get_bank_provider",
    "register_bank_provider",
]
