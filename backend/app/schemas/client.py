"""Client schemas (Pydantic v2)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ClientCreate(BaseModel):
    """Payload for creating a new client."""

    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=255)
    cpf_cnpj: str = Field(..., min_length=11, max_length=20)
    phone: str = Field(..., min_length=10, max_length=20)
    address: dict[str, Any] | None = None
    create_access: bool = Field(False, description="Create login credentials for the client")
    password: str | None = Field(None, min_length=8, max_length=128)


class ClientUpdate(BaseModel):
    """Payload for updating client data."""

    email: EmailStr | None = None
    full_name: str | None = Field(None, min_length=2, max_length=255)
    cpf_cnpj: str | None = Field(None, min_length=11, max_length=20)
    phone: str | None = Field(None, min_length=10, max_length=20)
    address: dict[str, Any] | None = None
    status: str | None = Field(None, pattern=r"^(active|inactive|defaulter)$")


class ClientResponse(BaseModel):
    """Client read response."""

    id: UUID
    company_id: UUID
    profile_id: UUID | None = None
    email: str
    full_name: str
    cpf_cnpj: str
    phone: str
    address: dict[str, Any] | None = None
    documents: list[Any] | None = None
    status: str
    asaas_customer_id: str | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
