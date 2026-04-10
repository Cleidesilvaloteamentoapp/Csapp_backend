"""Schemas for staff account management."""

import uuid
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class StaffPermissions(BaseModel):
    view_clients: bool = False
    manage_clients: bool = False
    view_lots: bool = False
    manage_lots: bool = False
    view_financial: bool = False
    manage_financial: bool = False
    view_renegotiations: bool = False
    manage_renegotiations: bool = False
    view_rescissions: bool = False
    manage_rescissions: bool = False
    view_reports: bool = False
    view_service_requests: bool = False
    manage_service_requests: bool = False
    view_documents: bool = False
    manage_documents: bool = False
    view_sicredi: bool = False
    manage_sicredi: bool = False
    view_whatsapp: bool = False
    manage_whatsapp: bool = False
    view_financial_settings: bool = False
    manage_financial_settings: bool = False

    model_config = {"from_attributes": True}


class StaffCreateRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    cpf_cnpj: str = Field(..., min_length=11, max_length=20)
    phone: str = Field(..., min_length=8, max_length=20)
    password: str = Field(..., min_length=8)
    permissions: StaffPermissions = Field(default_factory=StaffPermissions)


class StaffUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    phone: Optional[str] = Field(None, min_length=8, max_length=20)
    password: Optional[str] = Field(None, min_length=8)
    permissions: Optional[StaffPermissions] = None


class StaffResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    full_name: str
    email: str
    cpf_cnpj: str
    phone: str
    is_active: bool
    permissions: Optional[StaffPermissions] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_profile(cls, profile) -> "StaffResponse":
        perms = None
        if profile.staff_permission is not None:
            perms = StaffPermissions.model_validate(profile.staff_permission)
        return cls(
            id=profile.id,
            company_id=profile.company_id,
            full_name=profile.full_name,
            email=profile.email,
            cpf_cnpj=profile.cpf_cnpj,
            phone=profile.phone,
            is_active=profile.is_active,
            permissions=perms,
        )


class StaffToggleResponse(BaseModel):
    id: uuid.UUID
    is_active: bool
    message: str
