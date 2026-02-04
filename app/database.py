from supabase import create_client, Client
from functools import lru_cache
from app.core.config import get_settings


@lru_cache()
def get_supabase_client() -> Client:
    """
    Get Supabase client with anon key (respects RLS)
    Use this for authenticated user operations
    """
    settings = get_settings()
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)


@lru_cache()
def get_supabase_admin_client() -> Client:
    """
    Get Supabase client with service role key (bypasses RLS)
    Use this ONLY for admin operations that require bypassing RLS
    CRITICAL: Never expose this client to user-facing operations without proper validation
    """
    settings = get_settings()
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def get_authenticated_client(access_token: str) -> Client:
    """
    Get Supabase client authenticated with user's access token
    This ensures RLS policies are applied based on the user's identity
    """
    settings = get_settings()
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    client.auth.set_session(access_token, "")
    return client
