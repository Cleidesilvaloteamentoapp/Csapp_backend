
"""Meta (Facebook) WhatsApp Cloud API provider adapter.

Uses the official Cloud API to send template messages and manage templates.
Requires: WABA ID, Phone Number ID, and a permanent System User access token.

Docs: https://developers.facebook.com/docs/whatsapp/cloud-api
Auth: Bearer token in Authorization header.
"""

from typing import Any, Optional

import httpx

from app.services.whatsapp.base import WhatsAppProviderBase
from app.services.whatsapp.schemas import ConnectionStatus, SendResult, TemplateInfo
from app.utils.logging import get_logger

logger = get_logger(__name__)

GRAPH_API_VERSION = "v21.0"
GRAPH_BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
DEFAULT_TIMEOUT = 30.0


class MetaCloudProvider(WhatsAppProviderBase):
    """Adapter for Meta WhatsApp Cloud API (template-based messaging)."""

    provider_name = "meta"

    def __init__(
        self,
        waba_id: str,
        phone_number_id: str,
        access_token: str,
    ) -> None:
        self._waba_id = waba_id
        self._phone_number_id = phone_number_id
        self._access_token = access_token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    async def send_text(self, to: str, body: str) -> SendResult:
        """Send a plain text message via Cloud API.

        Note: Outside the 24h session window this will fail.
        For notifications, use send_template instead.
        """
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"body": body},
        }
        return await self._send_message(payload, to)

    async def send_template(
        self,
        to: str,
        template_name: str,
        language: str = "pt_BR",
        components: Optional[list[dict[str, Any]]] = None,
    ) -> SendResult:
        """Send a pre-approved template message via Cloud API."""
        template_obj: dict[str, Any] = {
            "name": template_name,
            "language": {"code": language},
        }
        if components:
            template_obj["components"] = components

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "template",
            "template": template_obj,
        }
        return await self._send_message(payload, to)

    async def _send_message(self, payload: dict[str, Any], to: str) -> SendResult:
        """Internal: POST to /{phone_number_id}/messages."""
        url = f"{GRAPH_BASE_URL}/{self._phone_number_id}/messages"
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.post(url, json=payload, headers=self._headers())
                data = resp.json()

                if resp.status_code in (200, 201):
                    messages = data.get("messages", [])
                    msg_id = messages[0].get("id") if messages else None
                    logger.info("meta_message_sent", to=to, message_id=msg_id)
                    return SendResult(
                        success=True,
                        message_id=msg_id,
                        provider=self.provider_name,
                        raw_response=data,
                    )

                error_data = data.get("error", {})
                error_msg = error_data.get("message", f"HTTP {resp.status_code}")
                logger.error("meta_send_failed", to=to, status=resp.status_code, error=error_msg)
                return SendResult(
                    success=False,
                    provider=self.provider_name,
                    error=error_msg,
                    raw_response=data,
                )
        except Exception as exc:
            logger.error("meta_send_exception", to=to, error=str(exc))
            return SendResult(success=False, provider=self.provider_name, error=str(exc))

    # ------------------------------------------------------------------
    # Connection check
    # ------------------------------------------------------------------

    async def check_connection(self) -> ConnectionStatus:
        """Validate the access token and phone number by fetching phone number info."""
        url = f"{GRAPH_BASE_URL}/{self._phone_number_id}"
        params = {"fields": "verified_name,display_phone_number,quality_rating,platform_type"}
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.get(url, params=params, headers=self._headers())
                data = resp.json()

                if resp.status_code == 200:
                    return ConnectionStatus(
                        connected=True,
                        status="connected",
                        profile_name=data.get("verified_name"),
                        phone_number=data.get("display_phone_number"),
                        raw=data,
                    )

                error_data = data.get("error", {})
                return ConnectionStatus(
                    connected=False,
                    status="disconnected",
                    error=error_data.get("message", f"HTTP {resp.status_code}"),
                    raw=data,
                )
        except Exception as exc:
            logger.error("meta_status_exception", error=str(exc))
            return ConnectionStatus(connected=False, status="error", error=str(exc))

    # ------------------------------------------------------------------
    # Template management
    # ------------------------------------------------------------------

    async def list_templates(self, limit: int = 100) -> list[TemplateInfo]:
        """List message templates from the WABA."""
        url = f"{GRAPH_BASE_URL}/{self._waba_id}/message_templates"
        params: dict[str, Any] = {"limit": limit}
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.get(url, params=params, headers=self._headers())
                data = resp.json()

                if resp.status_code != 200:
                    logger.error("meta_list_templates_failed", status=resp.status_code)
                    return []

                templates = []
                for t in data.get("data", []):
                    templates.append(TemplateInfo(
                        id=t.get("id"),
                        name=t.get("name", ""),
                        status=t.get("status", "UNKNOWN"),
                        category=t.get("category", ""),
                        language=t.get("language", "pt_BR"),
                        components=t.get("components", []),
                        raw=t,
                    ))
                return templates
        except Exception as exc:
            logger.error("meta_list_templates_exception", error=str(exc))
            return []

    async def create_template(self, template_data: dict[str, Any]) -> TemplateInfo:
        """Create a new message template in the WABA.

        template_data should follow Meta's template creation format:
        {
            "name": "template_name",
            "language": "pt_BR",
            "category": "UTILITY",  # or MARKETING, AUTHENTICATION
            "components": [...]
        }
        """
        url = f"{GRAPH_BASE_URL}/{self._waba_id}/message_templates"
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.post(url, json=template_data, headers=self._headers())
                data = resp.json()

                if resp.status_code in (200, 201):
                    logger.info("meta_template_created", name=template_data.get("name"))
                    return TemplateInfo(
                        id=data.get("id"),
                        name=template_data.get("name", ""),
                        status=data.get("status", "PENDING"),
                        category=template_data.get("category", ""),
                        language=template_data.get("language", "pt_BR"),
                        components=template_data.get("components", []),
                        raw=data,
                    )

                error_data = data.get("error", {})
                error_msg = error_data.get("message", f"HTTP {resp.status_code}")
                raise ValueError(f"Failed to create template: {error_msg}")
        except ValueError:
            raise
        except Exception as exc:
            logger.error("meta_create_template_exception", error=str(exc))
            raise ValueError(f"Failed to create template: {exc}") from exc

    async def get_template(self, template_name: str) -> Optional[TemplateInfo]:
        """Get a specific template by name."""
        url = f"{GRAPH_BASE_URL}/{self._waba_id}/message_templates"
        params = {"name": template_name}
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.get(url, params=params, headers=self._headers())
                data = resp.json()

                if resp.status_code != 200:
                    return None

                templates = data.get("data", [])
                if not templates:
                    return None

                t = templates[0]
                return TemplateInfo(
                    id=t.get("id"),
                    name=t.get("name", ""),
                    status=t.get("status", "UNKNOWN"),
                    category=t.get("category", ""),
                    language=t.get("language", "pt_BR"),
                    components=t.get("components", []),
                    raw=t,
                )
        except Exception as exc:
            logger.error("meta_get_template_exception", name=template_name, error=str(exc))
            return None

    async def delete_template(self, template_name: str) -> bool:
        """Delete a message template by name."""
        url = f"{GRAPH_BASE_URL}/{self._waba_id}/message_templates"
        params = {"name": template_name}
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.delete(url, params=params, headers=self._headers())
                if resp.status_code == 200:
                    logger.info("meta_template_deleted", name=template_name)
                    return True

                data = resp.json()
                error_msg = data.get("error", {}).get("message", f"HTTP {resp.status_code}")
                logger.error("meta_delete_template_failed", name=template_name, error=error_msg)
                return False
        except Exception as exc:
            logger.error("meta_delete_template_exception", name=template_name, error=str(exc))
            return False
