from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from app.models.enums import ClientStatus


class AddressSchema(BaseModel):
    street: str
    number: str
    complement: Optional[str] = None
    neighborhood: str
    city: str
    state: str
    zip_code: str
    country: str = "Brasil"


class ClientCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=2, max_length=100)
    cpf_cnpj: str = Field(..., min_length=11, max_length=18)
    phone: str = Field(..., min_length=10, max_length=20)
    address: Optional[AddressSchema] = None


class ClientUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    phone: Optional[str] = Field(None, min_length=10, max_length=20)
    address: Optional[AddressSchema] = None
    status: Optional[ClientStatus] = None


class ClientResponse(BaseModel):
    id: str
    profile_id: str
    email: str
    full_name: str
    cpf_cnpj: str
    phone: str
    address: Optional[dict] = None
    documents: Optional[List[str]] = None
    status: ClientStatus
    asaas_customer_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ClientListResponse(BaseModel):
    items: List[ClientResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ClientFilters(BaseModel):
    status: Optional[ClientStatus] = None
    search: Optional[str] = None
    page: int = 1
    page_size: int = 20
