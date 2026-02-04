from fastapi import APIRouter, Depends, HTTPException, status
from typing import Annotated
from supabase import Client

from app.api.deps import get_db, get_admin_db, get_current_user_profile, require_admin_role
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    SignupRequest,
    UserResponse,
    TokenRefreshRequest,
    PasswordResetRequest
)
from app.models.enums import UserRole

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    db: Annotated[Client, Depends(get_db)]
):
    """Authenticate user and return tokens"""
    try:
        response = db.auth.sign_in_with_password({
            "email": request.email,
            "password": request.password
        })
        
        if not response.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )
        
        profile = db.table("profiles").select("*").eq("id", response.user.id).single().execute()
        
        return LoginResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
            token_type="bearer",
            user={
                "id": response.user.id,
                "email": response.user.email,
                "role": profile.data.get("role") if profile.data else "client",
                "full_name": profile.data.get("full_name") if profile.data else ""
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    request: SignupRequest,
    admin: Annotated[dict, Depends(require_admin_role)],
    admin_db: Annotated[Client, Depends(get_admin_db)]
):
    """
    Create new user account (Admin only)
    Creates auth user, profile, and optionally client record
    """
    try:
        auth_response = admin_db.auth.admin.create_user({
            "email": request.email,
            "password": request.password,
            "email_confirm": True,
            "user_metadata": {
                "full_name": request.full_name,
                "role": request.role.value
            }
        })
        
        if not auth_response.user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create user"
            )
        
        user_id = auth_response.user.id
        
        profile_data = {
            "id": user_id,
            "full_name": request.full_name,
            "cpf_cnpj": request.cpf_cnpj,
            "phone": request.phone,
            "role": request.role.value
        }
        
        profile = admin_db.table("profiles").insert(profile_data).execute()
        
        if not profile.data:
            admin_db.auth.admin.delete_user(user_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create profile"
            )
        
        return UserResponse(
            id=user_id,
            email=request.email,
            full_name=request.full_name,
            cpf_cnpj=request.cpf_cnpj,
            phone=request.phone,
            role=request.role,
            created_at=profile.data[0].get("created_at", "")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create user: {str(e)}"
        )


@router.post("/logout")
async def logout(
    profile: Annotated[dict, Depends(get_current_user_profile)],
    db: Annotated[Client, Depends(get_db)]
):
    """Logout current user"""
    try:
        db.auth.sign_out()
        return {"message": "Logged out successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Logout failed: {str(e)}"
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    profile: Annotated[dict, Depends(get_current_user_profile)],
    db: Annotated[Client, Depends(get_db)]
):
    """Get current authenticated user data"""
    user = db.auth.get_user()
    
    return UserResponse(
        id=profile.get("id"),
        email=user.user.email if user and user.user else "",
        full_name=profile.get("full_name", ""),
        cpf_cnpj=profile.get("cpf_cnpj", ""),
        phone=profile.get("phone", ""),
        role=UserRole(profile.get("role", "client")),
        created_at=profile.get("created_at", "")
    )


@router.post("/refresh")
async def refresh_token(
    request: TokenRefreshRequest,
    db: Annotated[Client, Depends(get_db)]
):
    """Refresh access token"""
    try:
        response = db.auth.refresh_session(request.refresh_token)
        
        if not response.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        return {
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
            "token_type": "bearer"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token refresh failed"
        )


@router.post("/password-reset")
async def request_password_reset(
    request: PasswordResetRequest,
    db: Annotated[Client, Depends(get_db)]
):
    """Request password reset email"""
    try:
        db.auth.reset_password_email(request.email)
        return {"message": "Password reset email sent if account exists"}
    except Exception:
        return {"message": "Password reset email sent if account exists"}
