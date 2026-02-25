
"""Sicredi Webhook contract management.

Handles creating, querying, and updating webhook contracts
so the Sicredi API notifies your application on boleto events (e.g. LIQUIDACAO).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from app.services.sicredi.schemas import WebhookContratoRequest
from app.utils.logging import get_logger

if TYPE_CHECKING:
    from app.services.sicredi.client import SicrediClient

logger = get_logger(__name__)


class SicrediWebhooks:
    """Webhook contract operations for the Sicredi Cobrança API."""

    def __init__(self, client: SicrediClient):
        self._client = client

    @property
    def _base_url(self) -> str:
        return f"{self._client.credentials.boleto_base_url}/webhook"

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def criar_contrato(self, payload: WebhookContratoRequest) -> dict:
        """Register a new webhook contract with Sicredi.

        Args:
            payload: Webhook contract configuration.

        Returns:
            API response with contract ID and details.
        """
        url = f"{self._base_url}/contrato/"
        body = payload.model_dump(mode="json", exclude_none=True)

        logger.info(
            "sicredi_webhook_criar_contrato",
            url_destino=payload.url,
            eventos=payload.eventos,
        )
        return await self._client.request("POST", url, json=body)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    async def consultar_contratos(
        self,
        cooperativa: Optional[str] = None,
        posto: Optional[str] = None,
        beneficiario: Optional[str] = None,
    ) -> Any:
        """Query existing webhook contracts.

        Args:
            cooperativa: Override default cooperativa.
            posto: Override default posto.
            beneficiario: Override default beneficiary code.

        Returns:
            API response with contract list.
        """
        url = f"{self._base_url}/contratos/"
        params = {
            "cooperativa": cooperativa or self._client.credentials.cooperativa,
            "posto": posto or self._client.credentials.posto,
            "beneficiario": beneficiario or self._client.credentials.codigo_beneficiario,
        }

        logger.info("sicredi_webhook_consultar_contratos")
        return await self._client.request("GET", url, params=params)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def alterar_contrato(self, id_contrato: str, payload: WebhookContratoRequest) -> dict:
        """Update an existing webhook contract.

        Args:
            id_contrato: The contract ID returned during creation.
            payload: Updated contract configuration.

        Returns:
            API response.
        """
        url = f"{self._base_url}/contrato/{id_contrato}"
        body = payload.model_dump(mode="json", exclude_none=True)

        logger.info("sicredi_webhook_alterar_contrato", id_contrato=id_contrato)
        return await self._client.request("PUT", url, json=body)
