from typing import Optional, Tuple
from supabase import Client
from fastapi import HTTPException, status


async def verify_token(supabase: Client, token: str) -> Tuple[dict, str]:
    """
    Verify JWT token with Supabase and return user data and role.
    Returns tuple of (user_data, role)
    """
    try:
        user_response = supabase.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )
        
        user = user_response.user
        
        profile = supabase.table("profiles").select("*").eq("id", user.id).single().execute()
        
        if not profile.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User profile not found"
            )
        
        return profile.data, profile.data.get("role", "client")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {str(e)}"
        )


def require_admin(role: str) -> None:
    """Check if user has admin role"""
    if role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )


def require_client(role: str) -> None:
    """Check if user has client role"""
    if role not in ["client", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client access required"
        )
