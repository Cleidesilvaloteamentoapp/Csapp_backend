
"""Boleto schemas (Pydantic v2) for API responses and requests."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BoletoResponse(BaseModel):
    """Complete boleto response with all fields."""

    id: UUID
    company_id: UUID
    client_id: UUID
    
    nosso_numero: str
    seu_numero: str
    linha_digitavel: Optional[str] = None
    codigo_barras: Optional[str] = None
    
    tipo_cobranca: str
    especie_documento: str
    
    data_vencimento: date
    data_emissao: date
    data_liquidacao: Optional[date] = None
    
    valor: Decimal
    valor_liquidacao: Optional[Decimal] = None
    
    status: str
    
    txid: Optional[str] = None
    qr_code: Optional[str] = None
    
    invoice_id: Optional[UUID] = None
    
    pagador_data: Optional[dict] = None
    raw_response: Optional[dict] = None
    
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BoletoListResponse(BaseModel):
    """Simplified boleto response for list views."""

    id: UUID
    client_id: UUID
    
    nosso_numero: str
    seu_numero: str
    linha_digitavel: Optional[str] = None
    
    tipo_cobranca: str
    data_vencimento: date
    data_emissao: date
    data_liquidacao: Optional[date] = None
    
    valor: Decimal
    valor_liquidacao: Optional[Decimal] = None
    status: str
    
    pagador_data: Optional[dict] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BoletoClientInfo(BaseModel):
    """Client information embedded in boleto response."""

    id: UUID
    full_name: str
    cpf_cnpj: str
    email: str
    phone: str


class BoletoWithClientResponse(BaseModel):
    """Boleto response with embedded client information."""

    id: UUID
    nosso_numero: str
    seu_numero: str
    linha_digitavel: Optional[str] = None
    codigo_barras: Optional[str] = None
    
    tipo_cobranca: str
    data_vencimento: date
    data_emissao: date
    data_liquidacao: Optional[date] = None
    
    valor: Decimal
    valor_liquidacao: Optional[Decimal] = None
    status: str
    
    txid: Optional[str] = None
    qr_code: Optional[str] = None
    
    client: Optional[BoletoClientInfo] = None
    
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BoletoUpdateRequest(BaseModel):
    """Request to update boleto fields (status, payment info)."""

    status: Optional[str] = Field(None, pattern="^(NORMAL|LIQUIDADO|VENCIDO|CANCELADO)$")
    data_liquidacao: Optional[date] = None
    valor_liquidacao: Optional[Decimal] = None
    raw_response: Optional[dict] = None
