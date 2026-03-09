
"""API-facing Pydantic v2 schemas for Sicredi boleto management.

These schemas define the request/response contracts for the FastAPI endpoints.
They bridge the application's domain models with the Sicredi service module.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Credential Management (Admin only)
# ---------------------------------------------------------------------------

class SicrediCredentialCreate(BaseModel):
    """Payload for registering Sicredi credentials for a company."""

    x_api_key: str = Field(..., min_length=10, description="UUID token from Sicredi developer portal")
    username: str = Field(..., min_length=3, description="Beneficiário + Cooperativa code")
    password: str = Field(..., min_length=3, description="Access code from Internet Banking")
    cooperativa: str = Field(..., min_length=2, max_length=10)
    posto: str = Field(..., min_length=1, max_length=10)
    codigo_beneficiario: str = Field(..., min_length=1, max_length=20)
    environment: str = Field("production", pattern="^(sandbox|production)$")


class SicrediCredentialUpdate(BaseModel):
    """Payload for updating Sicredi credentials."""

    x_api_key: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    cooperativa: Optional[str] = None
    posto: Optional[str] = None
    codigo_beneficiario: Optional[str] = None
    environment: Optional[str] = Field(None, pattern="^(sandbox|production)$")
    is_active: Optional[bool] = None


class SicrediCredentialResponse(BaseModel):
    """Response for Sicredi credential (sensitive fields masked)."""

    id: UUID
    company_id: UUID
    cooperativa: str
    posto: str
    codigo_beneficiario: str
    environment: str
    is_active: bool
    webhook_contract_id: Optional[str] = None
    has_valid_token: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def compute_has_valid_token(cls, data):
        """Compute has_valid_token from the DB model's token_expires_at."""
        if hasattr(data, "token_expires_at"):
            expires = data.token_expires_at
            if expires and isinstance(expires, datetime):
                data = dict(data.__dict__) if not isinstance(data, dict) else data
                from datetime import timezone as tz
                data["has_valid_token"] = expires > datetime.now(tz.utc)
                return data
        if isinstance(data, dict) and data.get("token_expires_at"):
            expires = data["token_expires_at"]
            if isinstance(expires, datetime):
                from datetime import timezone as tz
                data["has_valid_token"] = expires > datetime.now(tz.utc)
        return data


# ---------------------------------------------------------------------------
# Pagador (Payer)
# ---------------------------------------------------------------------------

class PagadorRequest(BaseModel):
    """Payer data for boleto creation via API."""

    tipo_pessoa: str = Field(..., description="PESSOA_FISICA or PESSOA_JURIDICA")
    documento: str = Field(..., description="CPF or CNPJ (digits only)")
    nome: str = Field(..., max_length=40)
    endereco: str = Field(..., max_length=40)
    cidade: str = Field(..., max_length=20)
    uf: str = Field(..., min_length=2, max_length=2)
    cep: str = Field(..., description="CEP with 8 digits")
    email: Optional[str] = None
    telefone: Optional[str] = None


class BeneficiarioFinalRequest(BaseModel):
    """Final beneficiary for boleto creation."""

    tipo_pessoa: str
    documento: str
    nome: str
    logradouro: str
    numero_endereco: Optional[int] = None
    complemento: Optional[str] = None
    cidade: str
    uf: str = Field(..., min_length=2, max_length=2)
    cep: int
    telefone: Optional[str] = None


# ---------------------------------------------------------------------------
# Boleto CRUD
# ---------------------------------------------------------------------------

class CriarBoletoAPIRequest(BaseModel):
    """API request for creating a boleto via admin panel."""

    tipo_cobranca: str = Field("NORMAL", description="NORMAL or HIBRIDO")
    pagador: PagadorRequest
    especie_documento: str = Field("DUPLICATA_MERCANTIL_INDICACAO")
    data_vencimento: date
    valor: Decimal = Field(..., gt=0)
    seu_numero: str = Field(..., max_length=15, description="Internal control number")
    
    # Client association: provide EITHER client_id (existing) OR create_client (new)
    client_id: Optional[UUID] = Field(None, description="Existing client UUID to link boleto")
    create_client: bool = Field(False, description="Create new client from pagador data")
    invoice_id: Optional[UUID] = Field(None, description="Optional invoice to link")

    # Optional
    beneficiario_final: Optional[BeneficiarioFinalRequest] = None
    nosso_numero: Optional[int] = None
    tipo_desconto: Optional[str] = None
    valor_desconto_1: Optional[Decimal] = None
    valor_desconto_2: Optional[Decimal] = None
    valor_desconto_3: Optional[Decimal] = None
    data_desconto_1: Optional[date] = None
    data_desconto_2: Optional[date] = None
    data_desconto_3: Optional[date] = None
    tipo_juros: Optional[str] = None
    juros: Optional[Decimal] = None
    tipo_multa: Optional[str] = None
    multa: Optional[Decimal] = None
    desconto_antecipado: Optional[Decimal] = None
    dias_protesto_auto: Optional[int] = None
    dias_negativacao_auto: Optional[int] = None
    validade_apos_vencimento: Optional[int] = None
    informativos: Optional[list[str]] = None
    mensagens: Optional[list[str]] = None
    postar_boleto: Optional[str] = None
    
    @model_validator(mode="after")
    def validate_client_association(self):
        """Ensure either client_id or create_client is provided."""
        if not self.client_id and not self.create_client:
            raise ValueError("Must provide either client_id (existing client) or create_client=true (new client)")
        if self.client_id and self.create_client:
            raise ValueError("Cannot specify both client_id and create_client. Choose one.")
        return self


class CriarBoletoAPIResponse(BaseModel):
    """API response after boleto creation."""

    boleto_id: UUID
    client_id: UUID
    linha_digitavel: Optional[str] = None
    codigo_barras: Optional[str] = None
    nosso_numero: Optional[str] = None
    txid: Optional[str] = None
    qr_code: Optional[str] = None


class ConsultaBoletoAPIResponse(BaseModel):
    """API response for boleto query."""

    nosso_numero: Optional[str] = None
    codigo_barras: Optional[str] = None
    linha_digitavel: Optional[str] = None
    situacao: Optional[str] = None
    data_vencimento: Optional[str] = None
    valor: Optional[Decimal] = None
    pagador: Optional[dict] = None
    tipo_cobranca: Optional[str] = None
    txid: Optional[str] = None
    qr_code: Optional[str] = None
    seu_numero: Optional[str] = None
    raw_data: Optional[dict] = None


# ---------------------------------------------------------------------------
# Boleto Instructions (Edit)
# ---------------------------------------------------------------------------

class AlterarVencimentoAPIRequest(BaseModel):
    """API request for changing boleto due date."""

    data_vencimento: date


class AlterarSeuNumeroAPIRequest(BaseModel):
    """API request for changing boleto internal number."""

    seu_numero: str = Field(..., max_length=15)


class AlterarDescontoAPIRequest(BaseModel):
    """API request for changing boleto discounts."""

    valor_desconto_1: Optional[Decimal] = None
    valor_desconto_2: Optional[Decimal] = None
    valor_desconto_3: Optional[Decimal] = None


class AlterarJurosAPIRequest(BaseModel):
    """API request for changing boleto interest."""

    valor_ou_percentual: str


class ConcederAbatimentoAPIRequest(BaseModel):
    """API request for granting an abatement."""

    valor_abatimento: Decimal


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------

class WebhookContratoAPIRequest(BaseModel):
    """API request for creating/updating a Sicredi webhook contract."""

    url: str = Field(..., description="HTTPS callback URL")
    eventos: list[str] = Field(default_factory=lambda: ["LIQUIDACAO"])
    nome_responsavel: Optional[str] = None
    email: Optional[str] = None
    telefone: Optional[str] = None


class WebhookEventResponse(BaseModel):
    """Standardized response from Sicredi webhook event processing."""

    status: str
    nosso_numero: Optional[str] = None
    movimento: Optional[str] = None
    valor_liquidacao: Optional[Decimal] = None
    invoice_id: Optional[str] = None
    detail: Optional[str] = None
