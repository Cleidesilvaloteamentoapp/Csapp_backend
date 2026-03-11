
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
    contract_number: Optional[str] = Field(None, max_length=50)
    matricula: Optional[str] = Field(None, max_length=50)
    address: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    create_access: bool = Field(False, description="Create login credentials for the client")
    password: Optional[str] = Field(None, min_length=8, max_length=128)


class ClientUpdate(BaseModel):
    """Payload for updating client data."""

    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    cpf_cnpj: Optional[str] = Field(None, min_length=11, max_length=20)
    phone: Optional[str] = Field(None, min_length=10, max_length=20)
    contract_number: Optional[str] = Field(None, max_length=50)
    matricula: Optional[str] = Field(None, max_length=50)
    address: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    status: Optional[str] = Field(None, pattern=r"^(ACTIVE|INACTIVE|DEFAULTER|IN_NEGOTIATION|RESCINDED)$")


class ClientResponse(BaseModel):
    """Client read response."""

    id: UUID
    company_id: UUID
    profile_id: Optional[UUID] = None
    email: str
    full_name: str
    cpf_cnpj: str
    phone: str
    contract_number: Optional[str] = None
    matricula: Optional[str] = None
    address: Optional[Dict[str, Any]] = None
    documents: Optional[List[Any]] = None
    notes: Optional[str] = None
    status: str
    asaas_customer_id: Optional[str] = None
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClientProfileResponse(BaseModel):
    """Client-facing profile response (no internal fields)."""

    id: UUID
    profile_id: Optional[UUID] = None
    full_name: str
    cpf_cnpj: str
    email: str
    phone: str
    contract_number: Optional[str] = None
    matricula: Optional[str] = None
    address: Optional[Dict[str, Any]] = None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClientProfileUpdate(BaseModel):
    """Payload for client self-update (limited fields)."""

    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, min_length=10, max_length=20)
    address: Optional[Dict[str, Any]] = None
