
"""Client schemas (Pydantic v2)."""

from datetime import datetime
from typing import Any, Optional, Dict, List
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ClientCreate(BaseModel):
    """Payload for creating a new client."""

    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=255)
    cpf_cnpj: str = Field(..., min_length=11, max_length=20)
    phone: str = Field(..., min_length=10, max_length=20)
    address: Optional[Dict[str, Any]] = None
    create_access: bool = Field(False, description="Create login credentials for the client")
    password: Optional[str] = Field(None, min_length=8, max_length=128)


class ClientUpdate(BaseModel):
    """Payload for updating client data."""

    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    cpf_cnpj: Optional[str] = Field(None, min_length=11, max_length=20)
    phone: Optional[str] = Field(None, min_length=10, max_length=20)
    address: Optional[Dict[str, Any]] = None
    status: Optional[str] = Field(None, pattern=r"^(active|inactive|defaulter)$")


class ClientResponse(BaseModel):
    """Client read response."""

    id: UUID
    company_id: UUID
    profile_id: Optional[UUID] = None
    email: str
    full_name: str
    cpf_cnpj: str
    phone: str
    address: Optional[Dict[str, Any]] = None
    documents: Optional[List[Any]] = None
    status: str
    asaas_customer_id: Optional[str] = None
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
