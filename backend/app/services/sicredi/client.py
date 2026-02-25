
"""High-level Sicredi API client that composes auth, boletos, and webhooks.

This is the main entry point for consumers. It manages the HTTP session,
automatic authentication, and provides access to sub-modules.

Usage:
    client = SicrediClient(credentials=creds)
    boleto = await client.boletos.criar(payload)
    result = await client.boletos.consultar_por_nosso_numero("211001293")
    await client.boletos.baixar("211001293")
"""

from typing import Any, Optional

import httpx

from app.services.sicredi.auth import SicrediAuth
from app.services.sicredi.boletos import SicrediBoletos
from app.services.sicredi.config import HTTP_TIMEOUT, SicrediCredentials
from app.services.sicredi.exceptions import (
    SicrediAuthError,
    SicrediError,
    SicrediNotFoundError,
    SicrediRateLimitError,
    SicrediTimeoutError,
    SicrediValidationError,
)
from app.services.sicredi.webhooks import SicrediWebhooks
from app.utils.logging import get_logger

logger = get_logger(__name__)


class SicrediClient:
    """Facade for all Sicredi Cobrança API operations.

    Attributes:
        boletos: Boleto CRUD and PDF operations.
        webhooks: Webhook contract management.
    """

    def __init__(self, credentials: SicrediCredentials):
        self._creds = credentials
        self._auth = SicrediAuth(credentials)

        # Sub-modules receive a reference to this client's request method
        self.boletos = SicrediBoletos(self)
        self.webhooks = SicrediWebhooks(self)

    @property
    def credentials(self) -> SicrediCredentials:
        return self._creds

    def _build_headers(self, access_token: str, extra: Optional[dict] = None) -> dict:
        """Build the standard Sicredi API headers."""
        headers = {
            "x-api-key": self._creds.x_api_key,
            "Authorization": f"Bearer {access_token}",
            "cooperativa": self._creds.cooperativa,
            "posto": self._creds.posto,
            "Content-Type": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    async def request(
        self,
        method: str,
        url: str,
        *,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
        data: Optional[dict] = None,
        extra_headers: Optional[dict] = None,
        timeout: int = HTTP_TIMEOUT,
        retry_on_401: bool = True,
        expect_binary: bool = False,
    ) -> Any:
        """Execute an authenticated HTTP request to the Sicredi API.

        Handles automatic token acquisition and 401 retry logic.

        Args:
            method: HTTP method (GET, POST, PATCH, PUT, DELETE).
            url: Full URL to call.
            json: JSON body payload.
            params: Query parameters.
            data: Form data payload.
            extra_headers: Additional headers to merge.
            timeout: Request timeout in seconds.
            retry_on_401: Whether to retry once after refreshing the token on 401.
            expect_binary: If True, return raw bytes instead of parsed JSON.

        Returns:
            Parsed JSON dict/list or raw bytes (if expect_binary).

        Raises:
            SicrediAuthError: Authentication/token errors.
            SicrediValidationError: 4xx validation errors.
            SicrediNotFoundError: 404/422 not-found errors.
            SicrediRateLimitError: 429 rate limiting.
            SicrediError: Any other API error.
        """
        access_token = await self._auth.get_access_token()
        headers = self._build_headers(access_token, extra_headers)

        # Override Content-Type for form data
        if data:
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        try:
            async with httpx.AsyncClient(timeout=timeout) as http:
                resp = await http.request(
                    method=method,
                    url=url,
                    json=json,
                    params=params,
                    data=data,
                    headers=headers,
                )
        except httpx.TimeoutException as exc:
            raise SicrediTimeoutError(detail=f"Request to {url} timed out: {exc}")

        logger.debug(
            "sicredi_api_response",
            method=method,
            url=url,
            status=resp.status_code,
        )

        # Handle 401 with one automatic retry
        if resp.status_code == 401 and retry_on_401:
            logger.warning("sicredi_401_retry", url=url)
            self._auth.invalidate()
            return await self.request(
                method, url,
                json=json, params=params, data=data,
                extra_headers=extra_headers, timeout=timeout,
                retry_on_401=False,
                expect_binary=expect_binary,
            )

        # Success
        if resp.status_code in (200, 201):
            if expect_binary:
                return resp.content
            try:
                return resp.json()
            except Exception:
                return resp.text

        # Error handling
        self._raise_for_status(resp, url)

    def _raise_for_status(self, resp: httpx.Response, url: str) -> None:
        """Map HTTP error codes to specific exceptions."""
        body = self._safe_body(resp)
        detail_msg = f"Sicredi API error (HTTP {resp.status_code}) at {url}: {body}"

        if resp.status_code == 401:
            raise SicrediAuthError(detail=detail_msg, status_code=401, raw_response=body if isinstance(body, dict) else {"raw": body})
        elif resp.status_code == 404:
            raise SicrediNotFoundError(detail=detail_msg, status_code=404, raw_response=body if isinstance(body, dict) else {"raw": body})
        elif resp.status_code == 422:
            raise SicrediNotFoundError(detail=detail_msg, status_code=422, raw_response=body if isinstance(body, dict) else {"raw": body})
        elif resp.status_code == 429:
            raise SicrediRateLimitError(detail=detail_msg, status_code=429, raw_response=body if isinstance(body, dict) else {"raw": body})
        elif 400 <= resp.status_code < 500:
            raise SicrediValidationError(detail=detail_msg, status_code=resp.status_code, raw_response=body if isinstance(body, dict) else {"raw": body})
        else:
            raise SicrediError(detail=detail_msg, status_code=resp.status_code, raw_response=body if isinstance(body, dict) else {"raw": body})

    @staticmethod
    def _safe_body(resp: httpx.Response) -> Any:
        """Attempt to parse response body as JSON."""
        try:
            return resp.json()
        except Exception:
            return resp.text
