
"""Client document schemas (Pydantic v2)."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

DOCUMENT_TYPE_PATTERN = (
    r"^(RG|CPF|COMPROVANTE_RESIDENCIA|CNH|CONTRATO|CERTIDAO_ESTADO_CIVIL|"
    r"COMPROVANTE_RENDA|MATRICULA|GUIA_INFORMACAO|IPTU|FOTOS_IMOVEL|OUTROS)$"
)


class ClientDocumentResponse(BaseModel):
    """Client document read response."""

    id: UUID
    company_id: UUID
    client_id: UUID
    document_type: str
    file_name: str
    file_path: str
    file_url: Optional[str] = None
    file_size: int
    description: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    status: str
    rejection_reason: Optional[str] = None
    visible_to_client: bool = False
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClientDocumentUpload(BaseModel):
    """Metadata sent alongside a file upload."""

    document_type: str = Field(..., pattern=DOCUMENT_TYPE_PATTERN)
    description: Optional[str] = Field(None, max_length=500)
    tags: Optional[list[str]] = Field(default=None, max_length=20)


class ClientDocumentUpdate(BaseModel):
    """Admin partial update — change category and/or tags."""

    document_type: Optional[str] = Field(default=None, pattern=DOCUMENT_TYPE_PATTERN)
    description: Optional[str] = Field(default=None, max_length=500)
    tags: Optional[list[str]] = Field(default=None, max_length=20)
    visible_to_client: Optional[bool] = Field(default=None)


class DocumentReviewRequest(BaseModel):
    """Admin request to approve or reject a document."""

    status: str = Field(..., pattern=r"^(APPROVED|REJECTED)$")
    rejection_reason: Optional[str] = Field(None, max_length=500)
