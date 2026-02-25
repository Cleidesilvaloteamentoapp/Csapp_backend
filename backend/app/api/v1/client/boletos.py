
"""Client-facing endpoints for viewing Sicredi boletos.

Allows authenticated clients to view their boletos and download PDFs
directly from the platform, without needing to contact the admin.
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_client_user
from app.models.invoice import Invoice
from app.models.client_lot import ClientLot
from app.models.user import Profile
from app.schemas.sicredi import ConsultaBoletoAPIResponse
from app.services import sicredi_service
from app.services.sicredi.exceptions import SicrediError
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/boletos", tags=["Client Boletos"])


@router.get("/{nosso_numero}", response_model=ConsultaBoletoAPIResponse)
async def consultar_meu_boleto(
    nosso_numero: str,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Query a boleto by nossoNumero (client must belong to the same company)."""
    client = await sicredi_service.get_sicredi_client(db, user.company_id)

    try:
        result = await client.boletos.consultar_por_nosso_numero(nosso_numero)
        await sicredi_service.persist_token_cache(db, user.company_id)
    except SicrediError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.detail)

    return ConsultaBoletoAPIResponse(
        nosso_numero=result.nossoNumero,
        codigo_barras=result.codigoBarras,
        linha_digitavel=result.linhaDigitavel,
        situacao=result.situacao,
        data_vencimento=result.dataVencimento,
        valor=result.valor,
        pagador=result.pagador,
        tipo_cobranca=result.tipoCobranca,
        txid=result.txid,
        qr_code=result.qrCode,
        seu_numero=result.seuNumero,
    )


@router.get("/{nosso_numero}/pdf")
async def baixar_pdf_boleto(
    nosso_numero: str,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Download a boleto PDF by first querying the linhaDigitavel."""
    client = await sicredi_service.get_sicredi_client(db, user.company_id)

    try:
        # First get the boleto to extract linhaDigitavel
        boleto = await client.boletos.consultar_por_nosso_numero(nosso_numero)
        if not boleto.linhaDigitavel:
            raise HTTPException(status_code=404, detail="Linha digitável not available for this boleto")

        pdf_bytes = await client.boletos.gerar_pdf(boleto.linhaDigitavel)
        await sicredi_service.persist_token_cache(db, user.company_id)
    except SicrediError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.detail)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=boleto_{nosso_numero}.pdf"},
    )
