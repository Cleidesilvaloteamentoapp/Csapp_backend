
"""Pydantic models for Sicredi Cobrança API request/response payloads.

These schemas mirror the Sicredi API contracts and are decoupled from
the application's own database schemas, making the module portable.
"""

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class SicrediTokenResponse(BaseModel):
    """Response from the Sicredi OAuth2 token endpoint."""

    access_token: str
    refresh_token: str
    expires_in: int
    refresh_expires_in: int
    token_type: str = "Bearer"


# ---------------------------------------------------------------------------
# Pagador (Payer)
# ---------------------------------------------------------------------------

class Pagador(BaseModel):
    """Payer data for boleto creation."""

    tipoPessoa: str = Field(..., description="PESSOA_FISICA or PESSOA_JURIDICA")
    documento: str = Field(..., description="CPF or CNPJ (digits only)")
    nome: str = Field(..., max_length=40)
    endereco: str = Field(..., max_length=40)
    cidade: str = Field(..., max_length=20)
    uf: str = Field(..., min_length=2, max_length=2)
    cep: str = Field(..., description="CEP with 8 digits")
    email: Optional[str] = Field(None, max_length=40)
    telefone: Optional[str] = Field(None, max_length=15)


class BeneficiarioFinal(BaseModel):
    """Final beneficiary (sacador/avalista) data."""

    tipoPessoa: str = Field(..., description="PESSOA_FISICA or PESSOA_JURIDICA")
    documento: str
    nome: str
    logradouro: str
    numeroEndereco: Optional[int] = None
    complemento: Optional[str] = None
    cidade: str
    uf: str = Field(..., min_length=2, max_length=2)
    cep: int
    telefone: Optional[str] = None


# ---------------------------------------------------------------------------
# Boleto Creation
# ---------------------------------------------------------------------------

class CriarBoletoRequest(BaseModel):
    """Payload for creating a new boleto via Sicredi API."""

    tipoCobranca: str = Field("NORMAL", description="NORMAL or HIBRIDO")
    codigoBeneficiario: str
    pagador: Pagador
    especieDocumento: str = Field("DUPLICATA_MERCANTIL_INDICACAO")
    dataVencimento: date
    valor: Decimal = Field(..., gt=0, decimal_places=2)
    seuNumero: str = Field(..., max_length=15, description="Internal control number")

    # Optional fields
    beneficiarioFinal: Optional[BeneficiarioFinal] = None
    nossoNumero: Optional[int] = None
    tipoDesconto: Optional[str] = None
    valorDesconto1: Optional[Decimal] = None
    valorDesconto2: Optional[Decimal] = None
    valorDesconto3: Optional[Decimal] = None
    dataDesconto1: Optional[date] = None
    dataDesconto2: Optional[date] = None
    dataDesconto3: Optional[date] = None
    tipoJuros: Optional[str] = None
    juros: Optional[Decimal] = None
    tipoMulta: Optional[str] = None
    multa: Optional[Decimal] = None
    descontoAntecipado: Optional[Decimal] = None
    diasProtestoAuto: Optional[int] = None
    diasNegativacaoAuto: Optional[int] = None
    validadeAposVencimento: Optional[int] = Field(None, description="Hybrid boleto: QR Code validity after due date")
    informativos: Optional[list[str]] = Field(None, max_length=5)
    mensagens: Optional[list[str]] = Field(None, max_length=4)
    postarBoleto: Optional[str] = None

    model_config = ConfigDict(json_encoders={date: lambda v: v.isoformat(), Decimal: lambda v: float(v)})

    def to_api_payload(self) -> dict:
        """Convert to dict suitable for the Sicredi API, stripping None values."""
        data = self.model_dump(mode="json", exclude_none=True)
        return data


class CriarBoletoResponse(BaseModel):
    """Response from boleto creation."""

    linhaDigitavel: Optional[str] = None
    codigoBarras: Optional[str] = None
    nossoNumero: Optional[str] = None
    txid: Optional[str] = None
    qrCode: Optional[str] = None

    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# Boleto Query
# ---------------------------------------------------------------------------

class ConsultaBoletoResponse(BaseModel):
    """Response from boleto query by nossoNumero."""

    nossoNumero: Optional[str] = None
    codigoBarras: Optional[str] = None
    linhaDigitavel: Optional[str] = None
    situacao: Optional[str] = None
    dataVencimento: Optional[str] = None
    valor: Optional[Decimal] = None
    pagador: Optional[dict] = None
    tipoCobranca: Optional[str] = None
    txid: Optional[str] = None
    qrCode: Optional[str] = None
    seuNumero: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class ConsultaLiquidadosResponse(BaseModel):
    """Response from liquidated boletos query."""

    items: list[dict] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# Boleto Instructions (Edit)
# ---------------------------------------------------------------------------

class AlterarVencimentoRequest(BaseModel):
    """Payload for changing boleto due date."""

    dataVencimento: date


class AlterarSeuNumeroRequest(BaseModel):
    """Payload for changing the internal control number."""

    seuNumero: str = Field(..., max_length=15)


class AlterarDescontoRequest(BaseModel):
    """Payload for changing discount values."""

    valorDesconto1: Optional[Decimal] = None
    valorDesconto2: Optional[Decimal] = None
    valorDesconto3: Optional[Decimal] = None


class AlterarJurosRequest(BaseModel):
    """Payload for changing interest rate."""

    valorOuPercentual: str


class ConcederAbatimentoRequest(BaseModel):
    """Payload for granting an abatement."""

    valorAbatimento: Decimal


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------

class WebhookContratoRequest(BaseModel):
    """Payload for creating/updating a webhook contract."""

    cooperativa: str
    posto: str
    codBeneficiario: str
    eventos: list[str] = Field(default_factory=lambda: ["LIQUIDACAO"])
    url: str = Field(..., description="HTTPS URL with TLS 1.2+")
    urlStatus: str = "ATIVO"
    contratoStatus: str = "ATIVO"
    nomeResponsavel: Optional[str] = None
    email: Optional[str] = None
    telefone: Optional[str] = None
    enviarIdTituloEmpresa: Optional[bool] = None


class WebhookEventPayload(BaseModel):
    """Payload received from Sicredi webhook notifications."""

    agencia: Optional[str] = None
    posto: Optional[str] = None
    beneficiario: Optional[str] = None
    nossoNumero: Optional[str] = None
    dataEvento: Optional[str] = None
    movimento: Optional[str] = None
    valorLiquidacao: Optional[Decimal] = None
    idEventoWebhook: Optional[str] = None
    idTituloEmpresa: Optional[str] = None

    model_config = ConfigDict(extra="allow")
