
"""Client-facing endpoints for viewing Sicredi boletos.

Allows authenticated clients to view their boletos and download PDFs
directly from the platform, without needing to contact the admin.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_client_user
from app.models.boleto import Boleto
from app.models.client import Client
from app.models.invoice import Invoice
from app.models.client_lot import ClientLot
from app.models.user import Profile
from app.schemas.boleto import BoletoListResponse
from app.schemas.sicredi import ConsultaBoletoAPIResponse
from app.services import segunda_via_service, sicredi_service
from app.services.sicredi.exceptions import SicrediError
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/boletos", tags=["Client Boletos"])


# ---------------------------------------------------------------------------
# Local DB listing – MUST be before {nosso_numero} catch-all
# ---------------------------------------------------------------------------

async def _get_client_for_user(db: AsyncSession, user: Profile) -> Client:
    row = await db.execute(
        select(Client).where(Client.profile_id == user.id, Client.company_id == user.company_id)
    )
    client = row.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client profile not found")
    return client


@router.get("", response_model=list[BoletoListResponse])
async def list_my_boletos(
    status: Optional[str] = Query(None, pattern=r"^(NORMAL|LIQUIDADO|VENCIDO|CANCELADO|NEGATIVADO|PENDING_APPROVAL)$"),
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """List all boletos from the local database for the authenticated client."""
    client = await _get_client_for_user(db, user)

    query = (
        select(Boleto)
        .where(Boleto.client_id == client.id, Boleto.company_id == user.company_id)
    )
    if status:
        query = query.where(Boleto.status == status)

    query = query.order_by(Boleto.data_vencimento.desc())
    rows = await db.execute(query)
    return [BoletoListResponse.model_validate(b) for b in rows.scalars().all()]


# ---------------------------------------------------------------------------
# Segunda Via (Second Copy) – MUST be before {nosso_numero} catch-all
# ---------------------------------------------------------------------------


async def _get_client_for_user_sv(db: AsyncSession, user: Profile) -> Client:
    row = await db.execute(
        select(Client).where(Client.profile_id == user.id, Client.company_id == user.company_id)
    )
    client = row.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client profile not found")
    return client


@router.get("/segunda-via/preview/{invoice_id}")
async def preview_segunda_via(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Preview corrected amount for an overdue invoice (penalty + interest)."""
    client = await _get_client_for_user_sv(db, user)

    # Verify the invoice belongs to this client
    row = await db.execute(
        select(Invoice)
        .join(ClientLot, ClientLot.id == Invoice.client_lot_id)
        .where(
            Invoice.id == invoice_id,
            ClientLot.client_id == client.id,
            Invoice.company_id == user.company_id,
        )
    )
    if not row.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Invoice not found")

    try:
        result = await segunda_via_service.preview_segunda_via(
            db, user.company_id, invoice_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "invoice_id": result["invoice_id"],
        "installment_number": result["installment_number"],
        "original_amount": float(result["original_amount"]),
        "penalty": float(result["penalty"]),
        "interest": float(result["interest"]),
        "corrected_amount": float(result["corrected_amount"]),
        "days_overdue": result["days_overdue"],
        "new_due_date": result["new_due_date"].isoformat(),
    }


@router.post("/segunda-via/issue/{invoice_id}")
async def issue_segunda_via(
    invoice_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: Profile = Depends(get_client_user),
):
    """Issue a second copy boleto with automatic penalty/interest calculation."""
    client = await _get_client_for_user_sv(db, user)

    # Verify the invoice belongs to this client
    row = await db.execute(
        select(Invoice)
        .join(ClientLot, ClientLot.id == Invoice.client_lot_id)
        .where(
            Invoice.id == invoice_id,
            ClientLot.client_id == client.id,
            Invoice.company_id == user.company_id,
        )
    )
    if not row.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Invoice not found")

    try:
        result = await segunda_via_service.issue_segunda_via(
            db, user.company_id, invoice_id,
            performed_by=user.id,
            ip_address=request.client.host if request.client else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "invoice_id": result["invoice_id"],
        "installment_number": result["installment_number"],
        "original_amount": float(result["original_amount"]),
        "penalty": float(result["penalty"]),
        "interest": float(result["interest"]),
        "corrected_amount": float(result["corrected_amount"]),
        "days_overdue": result["days_overdue"],
        "new_due_date": result["new_due_date"].isoformat(),
    }


# ---------------------------------------------------------------------------
# Sicredi Boleto queries – {nosso_numero} catch-all MUST be last
# ---------------------------------------------------------------------------

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
