
"""Sicredi OAuth2 authentication with automatic token lifecycle management.

Handles:
- Initial authentication via username/password (grant_type=password)
- Token refresh via refresh_token (grant_type=refresh_token)
- Automatic refresh before expiration with safety margin
- Thread-safe token caching on the credentials object
"""

import asyncio
import time

import httpx

from app.services.sicredi.config import (
    HTTP_TIMEOUT,
    TOKEN_REFRESH_MARGIN_SECONDS,
    SicrediCredentials,
)
from app.services.sicredi.exceptions import SicrediAuthError, SicrediTimeoutError
from app.services.sicredi.schemas import SicrediTokenResponse
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Module-level lock to prevent concurrent token refreshes per credentials instance
_token_locks: dict[int, asyncio.Lock] = {}


def _get_lock(creds: SicrediCredentials) -> asyncio.Lock:
    """Get or create an asyncio lock for a specific credentials instance."""
    key = id(creds)
    if key not in _token_locks:
        _token_locks[key] = asyncio.Lock()
    return _token_locks[key]


class SicrediAuth:
    """Manages OAuth2 token acquisition and refresh for the Sicredi API."""

    def __init__(self, credentials: SicrediCredentials):
        self._creds = credentials

    def _is_token_valid(self) -> bool:
        """Check if the current access_token is still valid (with safety margin)."""
        if not self._creds._access_token or not self._creds._token_expires_at:
            return False
        return time.time() < (self._creds._token_expires_at - TOKEN_REFRESH_MARGIN_SECONDS)

    def _is_refresh_valid(self) -> bool:
        """Check if the refresh_token can still be used."""
        if not self._creds._refresh_token or not self._creds._refresh_expires_at:
            return False
        return time.time() < (self._creds._refresh_expires_at - TOKEN_REFRESH_MARGIN_SECONDS)

    async def get_access_token(self) -> str:
        """Return a valid access_token, refreshing or re-authenticating as needed.

        This is the main entry point for consumers. It guarantees a valid token
        is returned, handling the full lifecycle transparently.
        """
        if self._is_token_valid():
            return self._creds._access_token  # type: ignore

        lock = _get_lock(self._creds)
        async with lock:
            # Double-check after acquiring lock (another coroutine may have refreshed)
            if self._is_token_valid():
                return self._creds._access_token  # type: ignore

            if self._is_refresh_valid():
                await self._refresh_token()
            else:
                await self._authenticate()

            return self._creds._access_token  # type: ignore

    async def _authenticate(self) -> None:
        """Perform initial authentication with username/password."""
        logger.info("sicredi_auth_password", username=self._creds.username, env=self._creds.environment.value)

        headers = {
            "x-api-key": self._creds.x_api_key,
            "context": "COBRANCA",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "password",
            "username": self._creds.username,
            "password": self._creds.password,
            "scope": "cobranca",
        }

        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                resp = await client.post(self._creds.auth_url, headers=headers, data=data)
        except httpx.TimeoutException as exc:
            raise SicrediTimeoutError(detail=f"Auth request timed out: {exc}")

        if resp.status_code not in (200, 201):
            logger.error("sicredi_auth_failed", status=resp.status_code, body=resp.text)
            raise SicrediAuthError(
                detail=f"Authentication failed (HTTP {resp.status_code}): {resp.text}",
                status_code=resp.status_code,
                raw_response=self._safe_parse(resp),
            )

        self._store_token(resp.json())
        logger.info("sicredi_auth_success", expires_in=self._creds._token_expires_at)

    async def _refresh_token(self) -> None:
        """Use the refresh_token to obtain a new access_token."""
        logger.info("sicredi_auth_refresh", username=self._creds.username)

        headers = {
            "x-api-key": self._creds.x_api_key,
            "context": "COBRANCA",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self._creds._refresh_token,
            "scope": "cobranca",
        }

        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                resp = await client.post(self._creds.auth_url, headers=headers, data=data)
        except httpx.TimeoutException as exc:
            raise SicrediTimeoutError(detail=f"Refresh request timed out: {exc}")

        if resp.status_code not in (200, 201):
            logger.warning("sicredi_refresh_failed", status=resp.status_code, body=resp.text)
            # Fallback to full authentication
            await self._authenticate()
            return

        self._store_token(resp.json())
        logger.info("sicredi_refresh_success")

    def _store_token(self, data: dict) -> None:
        """Store token data on the credentials object."""
        token = SicrediTokenResponse(**data)
        now = time.time()
        self._creds._access_token = token.access_token
        self._creds._refresh_token = token.refresh_token
        self._creds._token_expires_at = now + token.expires_in
        self._creds._refresh_expires_at = now + token.refresh_expires_in

    @staticmethod
    def _safe_parse(resp: httpx.Response) -> dict:
        """Attempt to parse response as JSON, fallback to text."""
        try:
            return resp.json()
        except Exception:
            return {"raw_text": resp.text}

    def invalidate(self) -> None:
        """Force token invalidation (useful after 401 errors)."""
        self._creds._access_token = None
        self._creds._refresh_token = None
        self._creds._token_expires_at = None
        self._creds._refresh_expires_at = None
