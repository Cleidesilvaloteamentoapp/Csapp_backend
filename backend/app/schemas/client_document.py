
"""Client document schemas (Pydantic v2)."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
    status: str
    rejection_reason: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClientDocumentUpload(BaseModel):
    """Metadata sent alongside a file upload."""

    document_type: str = Field(
        ..., pattern=r"^(RG|CPF|COMPROVANTE_RESIDENCIA|CNH|CONTRATO|OUTROS)$"
    )
    description: Optional[str] = Field(None, max_length=500)


class DocumentReviewRequest(BaseModel):
    """Admin request to approve or reject a document."""

    status: str = Field(..., pattern=r"^(APPROVED|REJECTED)$")
    rejection_reason: Optional[str] = Field(None, max_length=500)
