
"""Sicredi Boleto operations: create, query, edit, cancel, and PDF generation.

All methods receive typed Pydantic models and return parsed responses.
The HTTP communication is delegated to the parent SicrediClient.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from app.services.sicredi.schemas import (
    AlterarDescontoRequest,
    AlterarJurosRequest,
    AlterarSeuNumeroRequest,
    AlterarVencimentoRequest,
    ConcederAbatimentoRequest,
    ConsultaBoletoResponse,
    CriarBoletoRequest,
    CriarBoletoResponse,
)
from app.utils.logging import get_logger

if TYPE_CHECKING:
    from app.services.sicredi.client import SicrediClient

logger = get_logger(__name__)


class SicrediBoletos:
    """Boleto management operations for the Sicredi Cobrança API."""

    def __init__(self, client: SicrediClient):
        self._client = client

    @property
    def _base_url(self) -> str:
        return self._client.credentials.boleto_base_url

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def criar(self, payload: CriarBoletoRequest) -> CriarBoletoResponse:
        """Register a new boleto (traditional or hybrid).

        Args:
            payload: Boleto creation data.

        Returns:
            CriarBoletoResponse with linhaDigitavel, codigoBarras, nossoNumero,
            and optionally txid/qrCode for hybrid boletos.
        """
        url = f"{self._base_url}/boletos"
        body = payload.to_api_payload()

        logger.info(
            "sicredi_boleto_criar",
            tipo=payload.tipoCobranca,
            valor=float(payload.valor),
            vencimento=str(payload.dataVencimento),
            seu_numero=payload.seuNumero,
        )

        data = await self._client.request("POST", url, json=body)
        return CriarBoletoResponse(**data)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    async def consultar_por_nosso_numero(self, nosso_numero: str) -> ConsultaBoletoResponse:
        """Query a boleto by its nossoNumero.

        Args:
            nosso_numero: The bank-assigned boleto number.

        Returns:
            ConsultaBoletoResponse with full boleto details and status.
        """
        url = f"{self._base_url}/boletos"
        params = {
            "codigoBeneficiario": self._client.credentials.codigo_beneficiario,
            "nossoNumero": nosso_numero,
        }

        logger.info("sicredi_boleto_consulta_nn", nosso_numero=nosso_numero)
        data = await self._client.request("GET", url, params=params)
        return ConsultaBoletoResponse(**data)

    async def consultar_por_seu_numero(self, seu_numero: str) -> dict:
        """Query a registered boleto by its seuNumero (internal control number).

        Args:
            seu_numero: The beneficiary's internal control number.

        Returns:
            Raw API response dict.
        """
        url = f"{self._base_url}/boletos/cadastrados"
        params = {"seuNumero": seu_numero}

        logger.info("sicredi_boleto_consulta_seu_numero", seu_numero=seu_numero)
        return await self._client.request("GET", url, params=params)

    async def consultar_liquidados_dia(self, dia: str, codigo_beneficiario: Optional[str] = None) -> list[dict]:
        """Query boletos liquidated on a specific date.

        Args:
            dia: Date in DD/MM/YYYY format.
            codigo_beneficiario: Override the default beneficiary code.

        Returns:
            List of liquidated boleto dicts.
        """
        url = f"{self._base_url}/boletos/liquidados/dia"
        params = {
            "codigoBeneficiario": codigo_beneficiario or self._client.credentials.codigo_beneficiario,
            "dia": dia,
        }

        logger.info("sicredi_boleto_liquidados_dia", dia=dia)
        data = await self._client.request("GET", url, params=params)
        if isinstance(data, list):
            return data
        return data if isinstance(data, dict) else []

    # ------------------------------------------------------------------
    # PDF Generation
    # ------------------------------------------------------------------

    async def gerar_pdf(self, linha_digitavel: str) -> bytes:
        """Generate a PDF (second copy) of a boleto.

        Args:
            linha_digitavel: 47-digit barcode string (digits only).

        Returns:
            Raw PDF bytes.
        """
        url = f"{self._base_url}/boletos/pdf"
        params = {"linhaDigitavel": linha_digitavel}

        logger.info("sicredi_boleto_pdf", linha_digitavel=linha_digitavel[:10] + "...")
        return await self._client.request("GET", url, params=params, expect_binary=True)

    # ------------------------------------------------------------------
    # Instructions (Edit / Cancel)
    # ------------------------------------------------------------------

    async def baixar(self, nosso_numero: str) -> Any:
        """Cancel (baixa) a boleto.

        Args:
            nosso_numero: The bank-assigned boleto number.

        Returns:
            API response.
        """
        url = f"{self._base_url}/boletos/{nosso_numero}/baixa"
        extra_headers = {"codigoBeneficiario": self._client.credentials.codigo_beneficiario}

        logger.info("sicredi_boleto_baixa", nosso_numero=nosso_numero)
        return await self._client.request("PATCH", url, json={}, extra_headers=extra_headers)

    async def alterar_vencimento(self, nosso_numero: str, payload: AlterarVencimentoRequest) -> Any:
        """Change the due date of a boleto.

        Args:
            nosso_numero: The bank-assigned boleto number.
            payload: New due date.

        Returns:
            API response.
        """
        url = f"{self._base_url}/boletos/{nosso_numero}/data-vencimento"
        body = payload.model_dump(mode="json")
        extra_headers = {"codigoBeneficiario": self._client.credentials.codigo_beneficiario}

        logger.info("sicredi_boleto_alterar_vencimento", nosso_numero=nosso_numero, nova_data=str(payload.dataVencimento))
        return await self._client.request("PATCH", url, json=body, extra_headers=extra_headers)

    async def alterar_seu_numero(self, nosso_numero: str, payload: AlterarSeuNumeroRequest) -> Any:
        """Change the internal control number of a boleto.

        Args:
            nosso_numero: The bank-assigned boleto number.
            payload: New seuNumero.

        Returns:
            API response.
        """
        url = f"{self._base_url}/boletos/{nosso_numero}/seu-numero"
        body = payload.model_dump(mode="json")
        extra_headers = {"codigoBeneficiario": self._client.credentials.codigo_beneficiario}

        logger.info("sicredi_boleto_alterar_seu_numero", nosso_numero=nosso_numero)
        return await self._client.request("PATCH", url, json=body, extra_headers=extra_headers)

    async def alterar_desconto(self, nosso_numero: str, payload: AlterarDescontoRequest) -> Any:
        """Change discount values of a boleto.

        Args:
            nosso_numero: The bank-assigned boleto number.
            payload: Discount values.

        Returns:
            API response.
        """
        url = f"{self._base_url}/boletos/{nosso_numero}/desconto"
        body = payload.model_dump(mode="json", exclude_none=True)
        extra_headers = {"codigoBeneficiario": self._client.credentials.codigo_beneficiario}

        logger.info("sicredi_boleto_alterar_desconto", nosso_numero=nosso_numero)
        return await self._client.request("PATCH", url, json=body, extra_headers=extra_headers)

    async def alterar_juros(self, nosso_numero: str, payload: AlterarJurosRequest) -> Any:
        """Change interest rate of a boleto.

        Args:
            nosso_numero: The bank-assigned boleto number.
            payload: Interest value or percentage.

        Returns:
            API response.
        """
        url = f"{self._base_url}/boletos/{nosso_numero}/juros"
        body = payload.model_dump(mode="json")
        extra_headers = {"codigoBeneficiario": self._client.credentials.codigo_beneficiario}

        logger.info("sicredi_boleto_alterar_juros", nosso_numero=nosso_numero)
        return await self._client.request("PATCH", url, json=body, extra_headers=extra_headers)

    async def conceder_abatimento(self, nosso_numero: str, payload: ConcederAbatimentoRequest) -> Any:
        """Grant an abatement (post-issuance discount) on a boleto.

        Args:
            nosso_numero: The bank-assigned boleto number.
            payload: Abatement value.

        Returns:
            API response.
        """
        url = f"{self._base_url}/boletos/{nosso_numero}/conceder-abatimento"
        body = payload.model_dump(mode="json")
        extra_headers = {"codigoBeneficiario": self._client.credentials.codigo_beneficiario}

        logger.info("sicredi_boleto_conceder_abatimento", nosso_numero=nosso_numero)
        return await self._client.request("PATCH", url, json=body, extra_headers=extra_headers)

    async def cancelar_abatimento(self, nosso_numero: str) -> Any:
        """Cancel a previously granted abatement.

        Args:
            nosso_numero: The bank-assigned boleto number.

        Returns:
            API response.
        """
        url = f"{self._base_url}/boletos/{nosso_numero}/cancelar-abatimento"
        extra_headers = {"codigoBeneficiario": self._client.credentials.codigo_beneficiario}

        logger.info("sicredi_boleto_cancelar_abatimento", nosso_numero=nosso_numero)
        return await self._client.request("PATCH", url, json={}, extra_headers=extra_headers)

    async def negativar(self, nosso_numero: str) -> Any:
        """Request negativation for an overdue boleto.

        Args:
            nosso_numero: The bank-assigned boleto number (9 digits).

        Returns:
            API response with transactionId and statusComando.
        """
        url = f"{self._base_url}/boletos/{nosso_numero}/negativacao"
        extra_headers = {"codigoBeneficiario": self._client.credentials.codigo_beneficiario}

        logger.info("sicredi_boleto_negativar", nosso_numero=nosso_numero)
        return await self._client.request("PATCH", url, json={}, extra_headers=extra_headers)

    async def sustar_negativacao_baixar(self, nosso_numero: str) -> Any:
        """Cancel negativation and simultaneously cancel (baixa) the boleto.

        Args:
            nosso_numero: The bank-assigned boleto number (9 digits).

        Returns:
            API response with transactionId and statusComando.
        """
        url = f"{self._base_url}/boletos/{nosso_numero}/sustar-negativacao-baixar-titulo"
        extra_headers = {"codigoBeneficiario": self._client.credentials.codigo_beneficiario}

        logger.info("sicredi_boleto_sustar_negativacao_baixar", nosso_numero=nosso_numero)
        return await self._client.request("PATCH", url, json={}, extra_headers=extra_headers)
