"""Batch operation schemas (Pydantic v2) for bulk boleto creation and management."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.sicredi import BeneficiarioFinalRequest, PagadorRequest


# ---------------------------------------------------------------------------
# Batch Creation
# ---------------------------------------------------------------------------

class BatchCriarBoletosRequest(BaseModel):
    """Request for creating multiple boletos at once with configurable frequency."""

    client_id: UUID = Field(..., description="Existing client UUID")
    pagador: PagadorRequest
    valor: Decimal = Field(..., gt=0, description="Value per installment")
    frequency: str = Field(
        "MENSAL",
        pattern="^(MENSAL|TRIMESTRAL|SEMESTRAL|ANUAL)$",
        description="Billing frequency",
    )
    duration_months: int = Field(
        12, ge=1, le=12, description="Total duration in months (max 12 = one cycle)"
    )
    data_primeiro_vencimento: date = Field(
        ..., description="Due date of the first installment"
    )

    tipo_cobranca: str = Field("NORMAL", description="NORMAL or HIBRIDO")
    especie_documento: str = Field("DUPLICATA_MERCANTIL_INDICACAO")

    beneficiario_final: Optional[BeneficiarioFinalRequest] = None
    tipo_desconto: Optional[str] = None
    valor_desconto_1: Optional[Decimal] = None
    valor_desconto_2: Optional[Decimal] = None
    valor_desconto_3: Optional[Decimal] = None
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

    @model_validator(mode="after")
    def validate_installment_count(self):
        """Ensure duration / frequency produces at least 1 and at most 12 installments (one cycle)."""
        freq_months = {"MENSAL": 1, "TRIMESTRAL": 3, "SEMESTRAL": 6, "ANUAL": 12}
        interval = freq_months.get(self.frequency, 1)
        count = self.duration_months // interval
        if count < 1:
            raise ValueError(
                f"Duration {self.duration_months} months with frequency "
                f"{self.frequency} produces 0 installments"
            )
        if count > 12:
            raise ValueError(
                f"Maximum 12 installments allowed (one cycle), got {count}"
            )
        return self


# ---------------------------------------------------------------------------
# Batch Operations (bulk actions on existing boletos)
# ---------------------------------------------------------------------------

class BatchOperationRequest(BaseModel):
    """Request for performing bulk actions on multiple existing boletos."""

    nosso_numeros: list[str] = Field(
        ..., min_length=1, max_length=100, description="List of nossoNumero to operate on"
    )
    action: str = Field(
        ...,
        pattern="^(BAIXA|ALTERAR_VENCIMENTO|ALTERAR_JUROS|ALTERAR_DESCONTO|CONCEDER_ABATIMENTO|CANCELAR_ABATIMENTO|NEGATIVACAO|SUSTAR_NEGATIVACAO_BAIXAR)$",
        description="Bulk action to apply",
    )

    data_vencimento: Optional[date] = Field(
        None, description="New due date (required for ALTERAR_VENCIMENTO)"
    )
    valor_ou_percentual: Optional[str] = Field(
        None, description="Interest value or percentage (required for ALTERAR_JUROS)"
    )
    valor_desconto_1: Optional[Decimal] = None
    valor_desconto_2: Optional[Decimal] = None
    valor_desconto_3: Optional[Decimal] = None
    valor_abatimento: Optional[Decimal] = Field(
        None, description="Abatement value (required for CONCEDER_ABATIMENTO)"
    )

    @model_validator(mode="after")
    def validate_action_payload(self):
        """Ensure required fields are present for the chosen action."""
        if self.action == "ALTERAR_VENCIMENTO" and not self.data_vencimento:
            raise ValueError("data_vencimento is required for ALTERAR_VENCIMENTO")
        if self.action == "ALTERAR_JUROS" and not self.valor_ou_percentual:
            raise ValueError("valor_ou_percentual is required for ALTERAR_JUROS")
        if self.action == "CONCEDER_ABATIMENTO" and not self.valor_abatimento:
            raise ValueError("valor_abatimento is required for CONCEDER_ABATIMENTO")
        return self


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class BatchOperationResponse(BaseModel):
    """Response after enqueuing a batch operation."""

    batch_id: UUID
    type: str
    status: str
    total_items: int
    message: str


class BatchItemResult(BaseModel):
    """Result for a single item within a batch operation."""

    index: int
    nosso_numero: Optional[str] = None
    seu_numero: Optional[str] = None
    status: str = Field(..., description="SUCCESS or FAILED")
    detail: str = ""
    boleto_id: Optional[UUID] = None


class BatchStatusResponse(BaseModel):
    """Full status of a batch operation including progress and results."""

    id: UUID
    type: str
    status: str
    total_items: int
    completed_items: int
    failed_items: int
    progress_percent: float
    frequency: Optional[str] = None
    duration_months: Optional[int] = None
    error_summary: Optional[str] = None
    results: list[BatchItemResult] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
