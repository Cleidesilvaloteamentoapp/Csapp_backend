
"""Admin endpoints for Sicredi boleto management.

Provides full boleto lifecycle management:
- Credential CRUD (configure Sicredi API access per company)
- Boleto creation (traditional and hybrid with Pix QR Code)
- Boleto queries (by nossoNumero, seuNumero, liquidated by day)
- Boleto instructions (cancel, change due date, discounts, interest, etc.)
- PDF generation (second copy)
- Webhook contract management
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_company_admin
from app.models.user import Profile
from app.models.client import Client
from app.models.boleto import Boleto
from app.models.enums import ClientStatus, BoletoStatus
from sqlalchemy import select
from datetime import date as dt_date
from app.schemas.sicredi import (
    AlterarDescontoAPIRequest,
    AlterarJurosAPIRequest,
    AlterarSeuNumeroAPIRequest,
    AlterarVencimentoAPIRequest,
    ConcederAbatimentoAPIRequest,
    ConsultaBoletoAPIResponse,
    CriarBoletoAPIRequest,
    CriarBoletoAPIResponse,
    SicrediCredentialCreate,
    SicrediCredentialResponse,
    SicrediCredentialUpdate,
    WebhookContratoAPIRequest,
)
from app.services.sicredi.schemas import (
    AlterarDescontoRequest,
    AlterarJurosRequest,
    AlterarSeuNumeroRequest,
    AlterarVencimentoRequest,
    ConcederAbatimentoRequest,
    CriarBoletoRequest,
    Pagador,
    BeneficiarioFinal,
    WebhookContratoRequest,
)
from app.services import sicredi_service
from app.services.sicredi.exceptions import SicrediError
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/sicredi", tags=["Admin Sicredi"])


# ---------------------------------------------------------------------------
# Helper: convert API request to Sicredi module schema
# ---------------------------------------------------------------------------

def _build_pagador(p) -> Pagador:
    return Pagador(
        tipoPessoa=p.tipo_pessoa,
        documento=p.documento,
        nome=p.nome,
        endereco=p.endereco,
        cidade=p.cidade,
        uf=p.uf,
        cep=p.cep,
        email=p.email,
        telefone=p.telefone,
    )


def _build_beneficiario_final(b) -> BeneficiarioFinal:
    return BeneficiarioFinal(
        tipoPessoa=b.tipo_pessoa,
        documento=b.documento,
        nome=b.nome,
        logradouro=b.logradouro,
        numeroEndereco=b.numero_endereco,
        complemento=b.complemento,
        cidade=b.cidade,
        uf=b.uf,
        cep=b.cep,
        telefone=b.telefone,
    )


# ---------------------------------------------------------------------------
# Credential Management
# ---------------------------------------------------------------------------

@router.post("/credentials", response_model=SicrediCredentialResponse, status_code=status.HTTP_201_CREATED)
async def create_credential(
    payload: SicrediCredentialCreate,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Register Sicredi API credentials for the company."""
    cred = await sicredi_service.create_credential(
        db,
        company_id=admin.company_id,
        x_api_key=payload.x_api_key,
        username=payload.username,
        password=payload.password,
        cooperativa=payload.cooperativa,
        posto=payload.posto,
        codigo_beneficiario=payload.codigo_beneficiario,
        environment=payload.environment,
    )
    return SicrediCredentialResponse.model_validate(cred)


@router.get("/credentials", response_model=SicrediCredentialResponse)
async def get_credential(
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Get the active Sicredi credential for the company."""
    cred = await sicredi_service.get_credential(db, admin.company_id)
    if not cred:
        raise HTTPException(status_code=404, detail="No active Sicredi credentials found")
    return SicrediCredentialResponse.model_validate(cred)


@router.put("/credentials/{credential_id}", response_model=SicrediCredentialResponse)
async def update_credential(
    credential_id: str,
    payload: SicrediCredentialUpdate,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Update Sicredi API credentials."""
    from uuid import UUID as _UUID
    cred = await sicredi_service.update_credential(
        db,
        credential_id=_UUID(credential_id),
        company_id=admin.company_id,
        **payload.model_dump(exclude_none=True),
    )
    return SicrediCredentialResponse.model_validate(cred)


@router.delete("/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential(
    credential_id: str,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Deactivate Sicredi credentials."""
    from uuid import UUID as _UUID
    await sicredi_service.delete_credential(db, _UUID(credential_id), admin.company_id)


# ---------------------------------------------------------------------------
# Boleto Creation
# ---------------------------------------------------------------------------

@router.post("/boletos", response_model=CriarBoletoAPIResponse, status_code=status.HTTP_201_CREATED)
async def criar_boleto(
    payload: CriarBoletoAPIRequest,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Create a new boleto (traditional or hybrid with Pix QR Code)."""
    sicredi_client = await sicredi_service.get_sicredi_client(db, admin.company_id)

    # Step 1: Get or create client
    if payload.client_id:
        # Use existing client
        stmt = select(Client).where(
            Client.id == payload.client_id,
            Client.company_id == admin.company_id
        )
        result_db = await db.execute(stmt)
        client_record = result_db.scalar_one_or_none()
        
        if not client_record:
            raise HTTPException(status_code=404, detail="Client not found")
    else:
        # Create new client from pagador data
        client_record = Client(
            company_id=admin.company_id,
            email=payload.pagador.email or f"{payload.pagador.documento}@temp.email",
            full_name=payload.pagador.nome,
            cpf_cnpj=payload.pagador.documento,
            phone=payload.pagador.telefone or "00000000000",
            address={
                "endereco": payload.pagador.endereco,
                "cidade": payload.pagador.cidade,
                "uf": payload.pagador.uf,
                "cep": payload.pagador.cep,
            },
            status=ClientStatus.ACTIVE,
            created_by=admin.id,
        )
        db.add(client_record)
        await db.flush()
        logger.info(f"Created new client {client_record.id} for boleto")

    # Step 2: Call Sicredi API to create boleto
    pagador = _build_pagador(payload.pagador)
    beneficiario = _build_beneficiario_final(payload.beneficiario_final) if payload.beneficiario_final else None

    boleto_req = CriarBoletoRequest(
        tipoCobranca=payload.tipo_cobranca,
        codigoBeneficiario=sicredi_client.credentials.codigo_beneficiario,
        pagador=pagador,
        especieDocumento=payload.especie_documento,
        dataVencimento=payload.data_vencimento,
        valor=payload.valor,
        seuNumero=payload.seu_numero,
        beneficiarioFinal=beneficiario,
        nossoNumero=payload.nosso_numero,
        tipoDesconto=payload.tipo_desconto,
        valorDesconto1=payload.valor_desconto_1,
        valorDesconto2=payload.valor_desconto_2,
        valorDesconto3=payload.valor_desconto_3,
        dataDesconto1=payload.data_desconto_1,
        dataDesconto2=payload.data_desconto_2,
        dataDesconto3=payload.data_desconto_3,
        tipoJuros=payload.tipo_juros,
        juros=payload.juros,
        tipoMulta=payload.tipo_multa,
        multa=payload.multa,
        descontoAntecipado=payload.desconto_antecipado,
        diasProtestoAuto=payload.dias_protesto_auto,
        diasNegativacaoAuto=payload.dias_negativacao_auto,
        validadeAposVencimento=payload.validade_apos_vencimento,
        informativos=payload.informativos,
        mensagens=payload.mensagens,
        postarBoleto=payload.postar_boleto,
    )

    try:
        result = await sicredi_client.boletos.criar(boleto_req)
        await sicredi_service.persist_token_cache(db, admin.company_id)
    except SicrediError as exc:
        logger.error("sicredi_criar_boleto_error", detail=exc.detail)
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.detail)

    # Step 3: Persist boleto record in database
    boleto_record = Boleto(
        company_id=admin.company_id,
        client_id=client_record.id,
        nosso_numero=result.nossoNumero,
        seu_numero=payload.seu_numero,
        linha_digitavel=result.linhaDigitavel,
        codigo_barras=result.codigoBarras,
        tipo_cobranca=payload.tipo_cobranca,
        especie_documento=payload.especie_documento,
        data_vencimento=payload.data_vencimento,
        data_emissao=dt_date.today(),
        valor=payload.valor,
        status=BoletoStatus.NORMAL,
        txid=result.txid,
        qr_code=result.qrCode,
        invoice_id=payload.invoice_id,
        pagador_data=payload.pagador.model_dump(),
        raw_response=result.model_dump(mode="json"),
        created_by=admin.id,
    )
    db.add(boleto_record)
    await db.commit()
    await db.refresh(boleto_record)
    
    logger.info(f"Boleto {boleto_record.nosso_numero} created and persisted for client {client_record.id}")

    return CriarBoletoAPIResponse(
        boleto_id=boleto_record.id,
        client_id=client_record.id,
        linha_digitavel=result.linhaDigitavel,
        codigo_barras=result.codigoBarras,
        nosso_numero=result.nossoNumero,
        txid=result.txid,
        qr_code=result.qrCode,
    )


# ---------------------------------------------------------------------------
# Boleto Queries (static-prefix routes MUST come before {nosso_numero} catch-all)
# ---------------------------------------------------------------------------

@router.get("/boletos/busca/seu-numero/{seu_numero}")
async def consultar_boleto_seu_numero(
    seu_numero: str,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Query a registered boleto by its seuNumero."""
    client = await sicredi_service.get_sicredi_client(db, admin.company_id)

    try:
        result = await client.boletos.consultar_por_seu_numero(seu_numero)
        await sicredi_service.persist_token_cache(db, admin.company_id)
    except SicrediError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.detail)

    return result


@router.get("/boletos/liquidados/{dia}")
async def consultar_liquidados_dia(
    dia: str,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Query boletos liquidated on a specific date (DD/MM/YYYY)."""
    client = await sicredi_service.get_sicredi_client(db, admin.company_id)

    try:
        result = await client.boletos.consultar_liquidados_dia(dia)
        await sicredi_service.persist_token_cache(db, admin.company_id)
    except SicrediError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.detail)

    return result


@router.get("/boletos/pdf/{linha_digitavel}")
async def gerar_pdf_boleto(
    linha_digitavel: str,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Generate a PDF (second copy) of a boleto from its linhaDigitavel."""
    client = await sicredi_service.get_sicredi_client(db, admin.company_id)

    try:
        pdf_bytes = await client.boletos.gerar_pdf(linha_digitavel)
        await sicredi_service.persist_token_cache(db, admin.company_id)
    except SicrediError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.detail)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=boleto_{linha_digitavel[:10]}.pdf"},
    )


@router.get("/boletos/{nosso_numero}", response_model=ConsultaBoletoAPIResponse)
async def consultar_boleto(
    nosso_numero: str,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Query a boleto by its nossoNumero."""
    client = await sicredi_service.get_sicredi_client(db, admin.company_id)

    try:
        result = await client.boletos.consultar_por_nosso_numero(nosso_numero)
        await sicredi_service.persist_token_cache(db, admin.company_id)
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
        raw_data=result.model_dump(mode="json"),
    )


# ---------------------------------------------------------------------------
# Boleto Instructions (Edit / Cancel)
# ---------------------------------------------------------------------------

@router.patch("/boletos/{nosso_numero}/baixa")
async def baixar_boleto(
    nosso_numero: str,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Cancel (baixa) a boleto."""
    client = await sicredi_service.get_sicredi_client(db, admin.company_id)

    try:
        result = await client.boletos.baixar(nosso_numero)
        await sicredi_service.persist_token_cache(db, admin.company_id)
    except SicrediError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.detail)

    return {"status": "ok", "detail": "Boleto cancelled", "response": result}


@router.patch("/boletos/{nosso_numero}/data-vencimento")
async def alterar_vencimento(
    nosso_numero: str,
    payload: AlterarVencimentoAPIRequest,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Change the due date of a boleto."""
    client = await sicredi_service.get_sicredi_client(db, admin.company_id)

    try:
        result = await client.boletos.alterar_vencimento(
            nosso_numero,
            AlterarVencimentoRequest(dataVencimento=payload.data_vencimento),
        )
        await sicredi_service.persist_token_cache(db, admin.company_id)
    except SicrediError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.detail)

    return {"status": "ok", "detail": "Due date updated", "response": result}


@router.patch("/boletos/{nosso_numero}/seu-numero")
async def alterar_seu_numero(
    nosso_numero: str,
    payload: AlterarSeuNumeroAPIRequest,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Change the internal control number of a boleto."""
    client = await sicredi_service.get_sicredi_client(db, admin.company_id)

    try:
        result = await client.boletos.alterar_seu_numero(
            nosso_numero,
            AlterarSeuNumeroRequest(seuNumero=payload.seu_numero),
        )
        await sicredi_service.persist_token_cache(db, admin.company_id)
    except SicrediError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.detail)

    return {"status": "ok", "detail": "seuNumero updated", "response": result}


@router.patch("/boletos/{nosso_numero}/desconto")
async def alterar_desconto(
    nosso_numero: str,
    payload: AlterarDescontoAPIRequest,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Change discount values of a boleto."""
    client = await sicredi_service.get_sicredi_client(db, admin.company_id)

    try:
        result = await client.boletos.alterar_desconto(
            nosso_numero,
            AlterarDescontoRequest(
                valorDesconto1=payload.valor_desconto_1,
                valorDesconto2=payload.valor_desconto_2,
                valorDesconto3=payload.valor_desconto_3,
            ),
        )
        await sicredi_service.persist_token_cache(db, admin.company_id)
    except SicrediError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.detail)

    return {"status": "ok", "detail": "Discounts updated", "response": result}


@router.patch("/boletos/{nosso_numero}/juros")
async def alterar_juros(
    nosso_numero: str,
    payload: AlterarJurosAPIRequest,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Change interest rate of a boleto."""
    client = await sicredi_service.get_sicredi_client(db, admin.company_id)

    try:
        result = await client.boletos.alterar_juros(
            nosso_numero,
            AlterarJurosRequest(valorOuPercentual=payload.valor_ou_percentual),
        )
        await sicredi_service.persist_token_cache(db, admin.company_id)
    except SicrediError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.detail)

    return {"status": "ok", "detail": "Interest updated", "response": result}


@router.patch("/boletos/{nosso_numero}/conceder-abatimento")
async def conceder_abatimento(
    nosso_numero: str,
    payload: ConcederAbatimentoAPIRequest,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Grant an abatement on a boleto."""
    client = await sicredi_service.get_sicredi_client(db, admin.company_id)

    try:
        result = await client.boletos.conceder_abatimento(
            nosso_numero,
            ConcederAbatimentoRequest(valorAbatimento=payload.valor_abatimento),
        )
        await sicredi_service.persist_token_cache(db, admin.company_id)
    except SicrediError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.detail)

    return {"status": "ok", "detail": "Abatement granted", "response": result}


@router.patch("/boletos/{nosso_numero}/cancelar-abatimento")
async def cancelar_abatimento(
    nosso_numero: str,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Cancel a previously granted abatement."""
    client = await sicredi_service.get_sicredi_client(db, admin.company_id)

    try:
        result = await client.boletos.cancelar_abatimento(nosso_numero)
        await sicredi_service.persist_token_cache(db, admin.company_id)
    except SicrediError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.detail)

    return {"status": "ok", "detail": "Abatement cancelled", "response": result}


# ---------------------------------------------------------------------------
# Webhook Contract Management
# ---------------------------------------------------------------------------

@router.post("/webhook/contrato", status_code=status.HTTP_201_CREATED)
async def criar_webhook_contrato(
    payload: WebhookContratoAPIRequest,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Register a webhook contract with Sicredi."""
    client = await sicredi_service.get_sicredi_client(db, admin.company_id)

    contrato_req = WebhookContratoRequest(
        cooperativa=client.credentials.cooperativa,
        posto=client.credentials.posto,
        codBeneficiario=client.credentials.codigo_beneficiario,
        eventos=payload.eventos,
        url=payload.url,
        urlStatus="ATIVO",
        contratoStatus="ATIVO",
        nomeResponsavel=payload.nome_responsavel,
        email=payload.email,
        telefone=payload.telefone,
    )

    try:
        result = await client.webhooks.criar_contrato(contrato_req)
        await sicredi_service.persist_token_cache(db, admin.company_id)
    except SicrediError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.detail)

    return result


@router.get("/webhook/contratos")
async def consultar_webhook_contratos(
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Query existing webhook contracts."""
    client = await sicredi_service.get_sicredi_client(db, admin.company_id)

    try:
        result = await client.webhooks.consultar_contratos()
        await sicredi_service.persist_token_cache(db, admin.company_id)
    except SicrediError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.detail)

    return result


@router.put("/webhook/contrato/{id_contrato}")
async def alterar_webhook_contrato(
    id_contrato: str,
    payload: WebhookContratoAPIRequest,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Update an existing webhook contract."""
    client = await sicredi_service.get_sicredi_client(db, admin.company_id)

    contrato_req = WebhookContratoRequest(
        cooperativa=client.credentials.cooperativa,
        posto=client.credentials.posto,
        codBeneficiario=client.credentials.codigo_beneficiario,
        eventos=payload.eventos,
        url=payload.url,
        urlStatus="ATIVO",
        contratoStatus="ATIVO",
        nomeResponsavel=payload.nome_responsavel,
        email=payload.email,
        telefone=payload.telefone,
    )

    try:
        result = await client.webhooks.alterar_contrato(id_contrato, contrato_req)
        await sicredi_service.persist_token_cache(db, admin.company_id)
    except SicrediError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.detail)

    return result
