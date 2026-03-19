
"""Abstract base class for bank provider integrations.

Every bank integration (Sicredi, Itaú, Bradesco, etc.) must implement
this interface so the rest of the application is bank-agnostic.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass
class BoletoResult:
    """Standardized boleto result returned by any bank provider."""

    nosso_numero: str
    seu_numero: str
    linha_digitavel: Optional[str] = None
    codigo_barras: Optional[str] = None
    status: str = "NORMAL"
    data_vencimento: Optional[date] = None
    data_emissao: Optional[date] = None
    valor: Optional[Decimal] = None
    txid: Optional[str] = None
    qr_code: Optional[str] = None
    pdf_url: Optional[str] = None
    raw_response: Optional[dict] = field(default_factory=dict)


@dataclass
class PagadorData:
    """Standardized payer data sent to the bank."""

    tipo_pessoa: str  # "F" (física) or "J" (jurídica)
    cpf_cnpj: str
    nome: str
    endereco: str
    cidade: str
    uf: str
    cep: str
    telefone: Optional[str] = None
    email: Optional[str] = None


class BankProvider(ABC):
    """Abstract interface for bank boleto operations."""

    @property
    @abstractmethod
    def bank_code(self) -> str:
        """FEBRABAN bank code (e.g. '748' for Sicredi)."""
        ...

    @property
    @abstractmethod
    def bank_name(self) -> str:
        """Human-readable bank name."""
        ...

    @abstractmethod
    async def authenticate(self) -> None:
        """Authenticate with the bank API. Called before operations."""
        ...

    @abstractmethod
    async def create_boleto(
        self,
        *,
        valor: Decimal,
        data_vencimento: date,
        pagador: PagadorData,
        seu_numero: str,
        tipo_cobranca: str = "NORMAL",
        especie_documento: str = "DUPLICATA_MERCANTIL_INDICACAO",
        mensagem: Optional[list[str]] = None,
        desconto: Optional[dict] = None,
        juros: Optional[dict] = None,
        multa: Optional[dict] = None,
    ) -> BoletoResult:
        """Create a boleto in the bank system."""
        ...

    @abstractmethod
    async def query_boleto(self, nosso_numero: str) -> BoletoResult:
        """Query a boleto by nossoNumero."""
        ...

    @abstractmethod
    async def cancel_boleto(self, nosso_numero: str) -> bool:
        """Request cancellation (baixa) of a boleto. Returns True if successful."""
        ...

    @abstractmethod
    async def get_pdf(self, nosso_numero: str) -> bytes:
        """Download the boleto PDF."""
        ...

    async def create_hybrid_boleto(
        self,
        *,
        valor: Decimal,
        data_vencimento: date,
        pagador: PagadorData,
        seu_numero: str,
        **kwargs,
    ) -> BoletoResult:
        """Create a hybrid boleto (boleto + Pix QR code).

        Default implementation: creates a normal boleto.
        Override in banks that support Pix integration.
        """
        return await self.create_boleto(
            valor=valor,
            data_vencimento=data_vencimento,
            pagador=pagador,
            seu_numero=seu_numero,
            tipo_cobranca="HIBRIDO",
            **kwargs,
        )

    async def parse_bank_statement(self, file_content: bytes, file_type: str = "cnab240") -> list[dict]:
        """Parse a bank statement (francesinha / retorno) file.

        Args:
            file_content: Raw file bytes
            file_type: Format — 'cnab240', 'cnab400', 'ofx'

        Returns list of dicts with standardized transaction data.
        Override per bank for specific file formats.
        """
        raise NotImplementedError(
            f"{self.bank_name} does not support bank statement parsing yet."
        )
