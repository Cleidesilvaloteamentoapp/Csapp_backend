
"""UAZAPI WhatsApp provider adapter.

Communicates with a pre-existing UAZAPI instance via its REST API.
The company stores base_url + instance_token; this adapter handles
/send/text and /instance/status.

Docs: uazapi-openapi-spec
Auth: header 'token' with the instance token.
"""

from typing import Any, Optional

import httpx

from app.services.whatsapp.base import WhatsAppProviderBase
from app.services.whatsapp.schemas import ConnectionStatus, SendResult
from app.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_TIMEOUT = 30.0


class UazapiProvider(WhatsAppProviderBase):
    """Adapter for UAZAPI WhatsApp API v2.0."""

    provider_name = "uazapi"

    def __init__(self, base_url: str, instance_token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = instance_token

    def _headers(self) -> dict[str, str]:
        return {"token": self._token, "Content-Type": "application/json"}

    async def send_text(self, to: str, body: str) -> SendResult:
        """Send a text message via UAZAPI /send/text."""
        payload: dict[str, Any] = {
            "number": to,
            "text": body,
        }
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.post(
                    f"{self._base_url}/send/text",
                    json=payload,
                    headers=self._headers(),
                )
                data = resp.json() if resp.status_code == 200 else {}

                if resp.status_code == 200:
                    logger.info("uazapi_text_sent", to=to)
                    return SendResult(
                        success=True,
                        message_id=data.get("id") or data.get("messageid"),
                        provider=self.provider_name,
                        raw_response=data,
                    )

                error_msg = data.get("error", f"HTTP {resp.status_code}")
                logger.error("uazapi_send_failed", to=to, status=resp.status_code, error=error_msg)
                return SendResult(
                    success=False,
                    provider=self.provider_name,
                    error=error_msg,
                    raw_response=data,
                )
        except Exception as exc:
            logger.error("uazapi_send_exception", to=to, error=str(exc))
            return SendResult(success=False, provider=self.provider_name, error=str(exc))

    async def send_template(
        self,
        to: str,
        template_name: str,
        language: str = "pt_BR",
        components: Optional[list[dict[str, Any]]] = None,
    ) -> SendResult:
        """UAZAPI does not use templates – falls back to sending plain text.

        For UAZAPI the caller should use send_text directly. This method
        is here to satisfy the interface; it returns a not-supported error.
        """
        return SendResult(
            success=False,
            provider=self.provider_name,
            error="UAZAPI does not support template messages. Use send_text instead.",
        )

    async def check_connection(self) -> ConnectionStatus:
        """Check UAZAPI instance status via GET /instance/status."""
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.get(
                    f"{self._base_url}/instance/status",
                    headers=self._headers(),
                )
                if resp.status_code != 200:
                    return ConnectionStatus(
                        connected=False,
                        status="error",
                        error=f"HTTP {resp.status_code}",
                    )

                data = resp.json()
                instance = data.get("instance", {})
                status_info = data.get("status", {})
                connected = status_info.get("connected", False)

                return ConnectionStatus(
                    connected=connected,
                    status=instance.get("status", "unknown"),
                    profile_name=instance.get("profileName"),
                    phone_number=status_info.get("jid", {}).get("user") if isinstance(status_info.get("jid"), dict) else None,
                    raw=data,
                )
        except Exception as exc:
            logger.error("uazapi_status_exception", error=str(exc))
            return ConnectionStatus(connected=False, status="error", error=str(exc))
