
"""Sicredi adapter — wraps the existing sicredi package behind the BankProvider interface.

This adapter delegates to the existing app.services.sicredi module so that no
existing Sicredi logic is duplicated. New bank integrations should implement
BankProvider directly instead of wrapping an existing module.
"""

from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.bank.base import BankProvider, BoletoResult, PagadorData
from app.utils.logging import get_logger

logger = get_logger(__name__)


class SicrediAdapter(BankProvider):
    """BankProvider implementation backed by the existing Sicredi integration."""

    def __init__(self, db: AsyncSession, company_id: UUID):
        self._db = db
        self._company_id = company_id
        self._client = None  # Lazy-loaded SicrediClient

    @property
    def bank_code(self) -> str:
        return "748"

    @property
    def bank_name(self) -> str:
        return "Sicredi"

    async def _get_client(self):
        if self._client is None:
            from app.services import sicredi_service
            self._client = await sicredi_service.get_sicredi_client(self._db, self._company_id)
        return self._client

    async def authenticate(self) -> None:
        """Authentication is handled lazily by get_sicredi_client."""
        await self._get_client()

    async def create_boleto(
        self,
        *,
        valor: Decimal,
        data_vencimento: date,
        pagador: PagadorData,
        seu_numero: str,
        tipo_cobranca: str = "NORMAL",
        especie_documento: str = "DUPLICATA_MERCANTIL_INDICACAO",
        mensagem: Optional[list[str]] = None,
        desconto: Optional[dict] = None,
        juros: Optional[dict] = None,
        multa: Optional[dict] = None,
    ) -> BoletoResult:
        client = await self._get_client()
        from app.services.sicredi.schemas import CriarBoletoRequest, Pagador

        pag = Pagador(
            tipoPessoa="PESSOA_FISICA" if pagador.tipo_pessoa == "F" else "PESSOA_JURIDICA",
            documento=pagador.cpf_cnpj,
            nome=pagador.nome,
            endereco=pagador.endereco,
            cidade=pagador.cidade,
            uf=pagador.uf,
            cep=pagador.cep,
            telefone=pagador.telefone or "",
            email=pagador.email or "",
        )

        req = CriarBoletoRequest(
            tipoCobranca=tipo_cobranca,
            especieDocumento=especie_documento,
            seuNumero=seu_numero,
            dataVencimento=data_vencimento.strftime("%Y-%m-%d"),
            valor=float(valor),
            pagador=pag,
        )

        result = await client.boletos.criar(req)
        from app.services import sicredi_service
        await sicredi_service.persist_token_cache(self._db, self._company_id)

        return BoletoResult(
            nosso_numero=result.nossoNumero,
            seu_numero=seu_numero,
            linha_digitavel=result.linhaDigitavel,
            codigo_barras=result.codigoBarras,
            status="NORMAL",
            data_vencimento=data_vencimento,
            valor=valor,
            txid=getattr(result, "txid", None),
            qr_code=getattr(result, "qrCode", None),
            raw_response=result.model_dump() if hasattr(result, "model_dump") else {},
        )

    async def query_boleto(self, nosso_numero: str) -> BoletoResult:
        client = await self._get_client()
        result = await client.boletos.consultar_por_nosso_numero(nosso_numero)
        from app.services import sicredi_service
        await sicredi_service.persist_token_cache(self._db, self._company_id)

        return BoletoResult(
            nosso_numero=result.nossoNumero,
            seu_numero=getattr(result, "seuNumero", ""),
            linha_digitavel=result.linhaDigitavel,
            codigo_barras=result.codigoBarras,
            status=result.situacao or "NORMAL",
            data_vencimento=result.dataVencimento,
            valor=Decimal(str(result.valor)) if result.valor else None,
            txid=result.txid,
            qr_code=result.qrCode,
        )

    async def cancel_boleto(self, nosso_numero: str) -> bool:
        client = await self._get_client()
        try:
            await client.boletos.baixar(nosso_numero)
            from app.services import sicredi_service
            await sicredi_service.persist_token_cache(self._db, self._company_id)
            return True
        except Exception as exc:
            logger.error("sicredi_cancel_failed", nosso_numero=nosso_numero, error=str(exc))
            return False

    async def get_pdf(self, nosso_numero: str) -> bytes:
        client = await self._get_client()
        boleto = await client.boletos.consultar_por_nosso_numero(nosso_numero)
        if not boleto.linhaDigitavel:
            raise ValueError("Linha digitável not available for PDF generation")
        pdf_bytes = await client.boletos.gerar_pdf(boleto.linhaDigitavel)
        from app.services import sicredi_service
        await sicredi_service.persist_token_cache(self._db, self._company_id)
        return pdf_bytes
