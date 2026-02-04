from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from app.models.enums import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=2, max_length=100)
    cpf_cnpj: str = Field(..., min_length=11, max_length=18)
    phone: str = Field(..., min_length=10, max_length=20)
    role: UserRole = UserRole.CLIENT


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    cpf_cnpj: str
    phone: str
    role: UserRole
    created_at: str


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordUpdateRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)
