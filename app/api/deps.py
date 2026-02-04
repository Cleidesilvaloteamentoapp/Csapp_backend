from typing import Annotated, Tuple
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import Client

from app.database import get_supabase_client, get_supabase_admin_client
from app.core.security import verify_token, require_admin


security = HTTPBearer()


async def get_db() -> Client:
    """Get Supabase client (respects RLS)"""
    return get_supabase_client()


async def get_admin_db() -> Client:
    """Get Supabase admin client (bypasses RLS) - USE WITH CAUTION"""
    return get_supabase_admin_client()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[Client, Depends(get_db)]
) -> Tuple[dict, str]:
    """
    Get current authenticated user from JWT token.
    Returns tuple of (profile_data, role)
    """
    token = credentials.credentials
    return await verify_token(db, token)


async def get_current_user_profile(
    current_user: Annotated[Tuple[dict, str], Depends(get_current_user)]
) -> dict:
    """Get current user's profile data"""
    profile, _ = current_user
    return profile


async def get_current_user_role(
    current_user: Annotated[Tuple[dict, str], Depends(get_current_user)]
) -> str:
    """Get current user's role"""
    _, role = current_user
    return role


async def require_admin_role(
    current_user: Annotated[Tuple[dict, str], Depends(get_current_user)]
) -> dict:
    """Dependency that requires admin role"""
    profile, role = current_user
    require_admin(role)
    return profile


async def require_client_role(
    current_user: Annotated[Tuple[dict, str], Depends(get_current_user)]
) -> dict:
    """Dependency that requires at least client role"""
    profile, role = current_user
    if role not in ["client", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client access required"
        )
    return profile


async def get_client_id_from_profile(
    profile: Annotated[dict, Depends(get_current_user_profile)],
    db: Annotated[Client, Depends(get_db)]
) -> str:
    """Get client ID from user's profile"""
    client = db.table("clients").select("id").eq("profile_id", profile["id"]).single().execute()
    
    if not client.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client profile not found"
        )
    
    return client.data["id"]
