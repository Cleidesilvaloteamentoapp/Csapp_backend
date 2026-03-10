
"""Service request (ticket) schemas (Pydantic v2)."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

class ServiceRequestMessageCreate(BaseModel):
    """Payload for adding a message to a ticket."""

    message: str = Field(..., min_length=1, max_length=5000)


class ServiceRequestMessageResponse(BaseModel):
    """Message read response."""

    id: UUID
    request_id: UUID
    author_id: UUID
    author_type: str
    author_name: Optional[str] = None
    message: str
    is_internal: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Service Requests
# ---------------------------------------------------------------------------

class ServiceRequestCreate(BaseModel):
    """Payload for creating a new service request."""

    service_type: str = Field(
        ..., pattern=r"^(MANUTENCAO|SUPORTE|FINANCEIRO|DOCUMENTACAO|OUTROS)$"
    )
    subject: str = Field(..., min_length=5, max_length=255)
    description: str = Field(..., min_length=10, max_length=5000)
    priority: str = Field("MEDIUM", pattern=r"^(LOW|MEDIUM|HIGH|URGENT)$")


class ServiceRequestResponse(BaseModel):
    """Service request read response."""

    id: UUID
    company_id: UUID
    client_id: UUID
    ticket_number: str
    service_type: str
    subject: str
    description: str
    status: str
    priority: str
    assigned_to: Optional[UUID] = None
    assignee_name: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ServiceRequestDetailResponse(ServiceRequestResponse):
    """Service request with messages."""

    messages: list[ServiceRequestMessageResponse] = []


class ServiceRequestAdminUpdate(BaseModel):
    """Admin payload to update a service request."""

    status: Optional[str] = Field(
        None, pattern=r"^(OPEN|IN_PROGRESS|WAITING_CLIENT|RESOLVED|CLOSED)$"
    )
    priority: Optional[str] = Field(
        None, pattern=r"^(LOW|MEDIUM|HIGH|URGENT)$"
    )
    assigned_to: Optional[UUID] = None


class ServiceRequestListResponse(BaseModel):
    """Paginated list response."""

    items: list[ServiceRequestResponse]
    total: int
    page: int
    per_page: int
