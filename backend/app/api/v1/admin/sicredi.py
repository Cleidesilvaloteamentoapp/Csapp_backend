
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
from app.core.deps import get_company_admin, require_permission
from app.models.user import Profile
from app.models.client import Client
from app.models.boleto import Boleto
from app.models.enums import ClientStatus, BoletoStatus, InvoiceStatus, WriteoffType, BoletoTag
from app.models.invoice import Invoice
from sqlalchemy import select
from datetime import date as dt_date, datetime, timezone
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
from app.models.batch_operation import BatchOperation
from app.schemas.batch import (
    BatchCriarBoletosRequest,
    BatchOperationRequest,
    BatchOperationResponse,
    BatchStatusResponse,
    BatchItemResult,
)
from app.tasks.batch_tasks import process_batch_creation, process_batch_operation
from app.core.audit import log_audit
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
    admin: Profile = Depends(require_permission("manage_sicredi")),
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
    admin: Profile = Depends(require_permission("manage_sicredi")),
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
    admin: Profile = Depends(require_permission("manage_sicredi")),
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
    admin: Profile = Depends(require_permission("manage_sicredi")),
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
    admin: Profile = Depends(require_permission("manage_sicredi")),
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
# Batch Operations (static-prefix routes — MUST come before {nosso_numero})
# ---------------------------------------------------------------------------

@router.post("/boletos/batch", response_model=BatchOperationResponse, status_code=status.HTTP_202_ACCEPTED)
async def batch_criar_boletos(
    payload: BatchCriarBoletosRequest,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_sicredi")),
):
    """Create multiple boletos in batch with configurable frequency and duration.

    The boletos are created asynchronously via a background task.
    Use GET /boletos/batch/{batch_id} to track progress.
    """
    # Verify client exists
    stmt = select(Client).where(
        Client.id == payload.client_id,
        Client.company_id == admin.company_id,
    )
    result_db = await db.execute(stmt)
    if not result_db.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Client not found")

    # Calculate number of installments
    freq_months = {"MENSAL": 1, "TRIMESTRAL": 3, "SEMESTRAL": 6, "ANUAL": 12}
    interval = freq_months.get(payload.frequency, 1)
    num_installments = payload.duration_months // interval

    # Persist batch operation record
    input_data = payload.model_dump(mode="json")
    input_data["client_id"] = str(payload.client_id)
    input_data["created_by"] = str(admin.id)
    input_data["data_primeiro_vencimento"] = payload.data_primeiro_vencimento.isoformat()

    batch = BatchOperation(
        company_id=admin.company_id,
        type="BATCH_CREATE",
        status="PENDING",
        client_id=payload.client_id,
        frequency=payload.frequency,
        duration_months=payload.duration_months,
        total_items=num_installments,
        input_data=input_data,
        results=[],
        created_by=admin.id,
    )
    db.add(batch)
    await db.commit()
    await db.refresh(batch)

    # Audit log
    await log_audit(
        db=db,
        user_id=admin.id,
        company_id=admin.company_id,
        table_name="batch_operations",
        operation="BATCH_CREATE",
        resource_id=str(batch.id),
        detail=f"Batch creation: {num_installments} boletos, client {payload.client_id}, frequency {payload.frequency}, duration {payload.duration_months} months",
    )
    await db.commit()

    # Enqueue Celery task
    process_batch_creation.delay(str(batch.id), str(admin.company_id))

    logger.info(
        "batch_creation_enqueued",
        batch_id=str(batch.id),
        num_installments=num_installments,
        frequency=payload.frequency,
    )

    return BatchOperationResponse(
        batch_id=batch.id,
        type=batch.type,
        status=batch.status,
        total_items=num_installments,
        message=f"Batch creation queued: {num_installments} boletos ({payload.frequency}, {payload.duration_months} months)",
    )


@router.post("/boletos/batch-operation", response_model=BatchOperationResponse, status_code=status.HTTP_202_ACCEPTED)
async def batch_operacao_boletos(
    payload: BatchOperationRequest,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_sicredi")),
):
    """Execute a bulk action on multiple existing boletos.

    Supported actions: BAIXA, ALTERAR_VENCIMENTO, ALTERAR_JUROS,
    ALTERAR_DESCONTO, CONCEDER_ABATIMENTO, CANCELAR_ABATIMENTO,
    NEGATIVACAO, SUSTAR_NEGATIVACAO_BAIXAR.

    Use GET /boletos/batch/{batch_id} to track progress.
    """
    action_type_map = {
        "BAIXA": "BATCH_BAIXA",
        "ALTERAR_VENCIMENTO": "BATCH_ALTERAR_VENCIMENTO",
        "ALTERAR_JUROS": "BATCH_ALTERAR_JUROS",
        "ALTERAR_DESCONTO": "BATCH_ALTERAR_DESCONTO",
        "CONCEDER_ABATIMENTO": "BATCH_CONCEDER_ABATIMENTO",
        "CANCELAR_ABATIMENTO": "BATCH_CANCELAR_ABATIMENTO",
        "NEGATIVACAO": "BATCH_NEGATIVACAO",
        "SUSTAR_NEGATIVACAO_BAIXAR": "BATCH_SUSTAR_NEGATIVACAO_BAIXAR",
    }

    batch_type = action_type_map.get(payload.action)
    if not batch_type:
        raise HTTPException(status_code=400, detail=f"Invalid action: {payload.action}")

    input_data = payload.model_dump(mode="json")
    if payload.data_vencimento:
        input_data["data_vencimento"] = payload.data_vencimento.isoformat()

    batch = BatchOperation(
        company_id=admin.company_id,
        type=batch_type,
        status="PENDING",
        total_items=len(payload.nosso_numeros),
        input_data=input_data,
        results=[],
        created_by=admin.id,
    )
    db.add(batch)
    await db.commit()
    await db.refresh(batch)

    # Audit log
    await log_audit(
        db=db,
        user_id=admin.id,
        company_id=admin.company_id,
        table_name="batch_operations",
        operation=f"BATCH_{payload.action}",
        resource_id=str(batch.id),
        detail=f"Batch operation: {payload.action} on {len(payload.nosso_numeros)} boletos (nosso_numeros: {', '.join(payload.nosso_numeros[:5])}{'...' if len(payload.nosso_numeros) > 5 else ''})",
    )
    await db.commit()

    # Enqueue Celery task
    process_batch_operation.delay(str(batch.id), str(admin.company_id))

    logger.info(
        "batch_operation_enqueued",
        batch_id=str(batch.id),
        action=payload.action,
        count=len(payload.nosso_numeros),
    )

    return BatchOperationResponse(
        batch_id=batch.id,
        type=batch.type,
        status=batch.status,
        total_items=len(payload.nosso_numeros),
        message=f"Batch {payload.action} queued for {len(payload.nosso_numeros)} boletos",
    )


@router.get("/boletos/batch/{batch_id}", response_model=BatchStatusResponse)
async def get_batch_status(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_sicredi")),
):
    """Get the status and progress of a batch operation."""
    from uuid import UUID as _UUID

    stmt = select(BatchOperation).where(
        BatchOperation.id == _UUID(batch_id),
        BatchOperation.company_id == admin.company_id,
    )
    result = await db.execute(stmt)
    batch = result.scalar_one_or_none()

    if not batch:
        raise HTTPException(status_code=404, detail="Batch operation not found")

    total = batch.total_items or 1
    progress = round(((batch.completed_items + batch.failed_items) / total) * 100, 1)

    raw_results = batch.results or []
    items = [
        BatchItemResult(
            index=r.get("index", 0),
            nosso_numero=r.get("nosso_numero"),
            seu_numero=r.get("seu_numero"),
            status=r.get("status", "PENDING"),
            detail=r.get("detail", ""),
            boleto_id=r.get("boleto_id"),
        )
        for r in raw_results
    ]

    return BatchStatusResponse(
        id=batch.id,
        type=batch.type,
        status=batch.status,
        total_items=batch.total_items,
        completed_items=batch.completed_items,
        failed_items=batch.failed_items,
        progress_percent=progress,
        frequency=batch.frequency,
        duration_months=batch.duration_months,
        error_summary=batch.error_summary,
        results=items,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
    )


# ---------------------------------------------------------------------------
# Boleto Queries (static-prefix routes MUST come before {nosso_numero} catch-all)
# ---------------------------------------------------------------------------

@router.get("/boletos/busca/seu-numero/{seu_numero}")
async def consultar_boleto_seu_numero(
    seu_numero: str,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_sicredi")),
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
    admin: Profile = Depends(require_permission("manage_sicredi")),
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
    admin: Profile = Depends(require_permission("manage_sicredi")),
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
    admin: Profile = Depends(require_permission("manage_sicredi")),
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

@router.post("/boletos/{nosso_numero}/sync")
async def sync_boleto_status(
    nosso_numero: str,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_sicredi")),
):
    """Sync local boleto status with the current status reported by Sicredi.

    Useful when the webhook was not received or processed (e.g. boleto was
    liquidated at Sicredi but the local DB still shows NORMAL).
    Maps Sicredi situacao → BoletoStatus and updates the boleto record plus
    any linked invoice.
    """
    sicredi_client = await sicredi_service.get_sicredi_client(db, admin.company_id)

    try:
        sicredi_data = await sicredi_client.boletos.consultar_por_nosso_numero(nosso_numero)
        await sicredi_service.persist_token_cache(db, admin.company_id)
    except SicrediError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.detail)

    situacao = (sicredi_data.situacao or "").upper()

    _SITUACAO_MAP = {
        "LIQUIDADO": BoletoStatus.LIQUIDADO,
        "BAIXADO": BoletoStatus.CANCELADO,
        "BAIXADO POR SOLICITACAO": BoletoStatus.CANCELADO,
        "VENCIDO": BoletoStatus.VENCIDO,
        "NEGATIVADO": BoletoStatus.NEGATIVADO,
        "NORMAL": BoletoStatus.NORMAL,
    }
    new_status = _SITUACAO_MAP.get(situacao)
    
    # Track if this is an external baixa (not from our platform)
    is_baixa_externa = situacao in ("BAIXADO", "BAIXADO POR SOLICITACAO")
    
    if not new_status:
        return {
            "status": "noop",
            "nosso_numero": nosso_numero,
            "sicredi_situacao": sicredi_data.situacao,
            "detail": f"Unknown situacao '{sicredi_data.situacao}'; no changes made.",
        }

    stmt = select(Boleto).where(
        Boleto.nosso_numero == nosso_numero,
        Boleto.company_id == admin.company_id,
    )
    db_result = await db.execute(stmt)
    boleto_record = db_result.scalar_one_or_none()

    if not boleto_record:
        raise HTTPException(status_code=404, detail="Boleto not found in local database")

    previous_status = boleto_record.status
    previous_writeoff_type = boleto_record.writeoff_type
    boleto_record.status = new_status
    
    # Track external baixa - only mark if not already tracked as manual
    if is_baixa_externa and previous_writeoff_type != WriteoffType.MANUAL_ADMIN:
        boleto_record.writeoff_type = WriteoffType.BAIXA_EXTERNA
        boleto_record.writeoff_reason = f"Baixa externa via Sicredi (situacao: {sicredi_data.situacao}). Sincronizado via endpoint /sync."
    
    if new_status == BoletoStatus.LIQUIDADO:
        if not boleto_record.data_liquidacao:
            boleto_record.data_liquidacao = datetime.now(timezone.utc).date()
        if boleto_record.invoice_id:
            inv_result = await db.execute(
                select(Invoice).where(Invoice.id == boleto_record.invoice_id)
            )
            linked_invoice = inv_result.scalar_one_or_none()
            if linked_invoice and linked_invoice.status != InvoiceStatus.PAID:
                linked_invoice.status = InvoiceStatus.PAID
                linked_invoice.paid_at = datetime.now(timezone.utc)

    await db.commit()

    logger.info(
        "sicredi_boleto_sync",
        nosso_numero=nosso_numero,
        previous_status=previous_status.value if previous_status else None,
        new_status=new_status.value,
        sicredi_situacao=sicredi_data.situacao,
    )

    return {
        "status": "synced",
        "nosso_numero": nosso_numero,
        "sicredi_situacao": sicredi_data.situacao,
        "previous_local_status": previous_status.value if previous_status else None,
        "new_local_status": new_status.value,
    }


@router.patch("/boletos/{nosso_numero}/baixa")
async def baixar_boleto(
    nosso_numero: str,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_sicredi")),
):
    """Cancel (baixa) a boleto."""
    client = await sicredi_service.get_sicredi_client(db, admin.company_id)

    try:
        result = await client.boletos.baixar(nosso_numero)
        await sicredi_service.persist_token_cache(db, admin.company_id)
    except SicrediError as exc:
        error_msg = str(exc.detail or "")
        
        # Handle 0077: título já liquidado
        if exc.status_code == 422 and ("0077" in error_msg or "já liquidado" in error_msg.lower()):
            stmt = select(Boleto).where(
                Boleto.nosso_numero == nosso_numero,
                Boleto.company_id == admin.company_id,
            )
            db_result = await db.execute(stmt)
            boleto_record = db_result.scalar_one_or_none()
            if boleto_record and boleto_record.status != BoletoStatus.LIQUIDADO:
                boleto_record.status = BoletoStatus.LIQUIDADO
                if not boleto_record.data_liquidacao:
                    boleto_record.data_liquidacao = datetime.now(timezone.utc).date()
                
                # Track manual action even when syncing already-liquidated boleto
                boleto_record.writeoff_type = WriteoffType.MANUAL_ADMIN
                boleto_record.writeoff_by = admin.id
                boleto_record.writeoff_reason = "Tentativa de baixa manual - boleto já liquidado no banco (sincronizado)"
                
                if boleto_record.invoice_id:
                    inv_result = await db.execute(
                        select(Invoice).where(Invoice.id == boleto_record.invoice_id)
                    )
                    linked_invoice = inv_result.scalar_one_or_none()
                    if linked_invoice and linked_invoice.status != InvoiceStatus.PAID:
                        linked_invoice.status = InvoiceStatus.PAID
                        linked_invoice.paid_at = datetime.now(timezone.utc)
                
                await log_audit(
                    db=db,
                    user_id=admin.id,
                    company_id=admin.company_id,
                    table_name="boletos",
                    operation="BAIXA_SYNC_LIQ",
                    resource_id=str(boleto_record.id),
                    detail=f"Boleto {nosso_numero} ja liquidado no Sicredi. Sincronizado por admin.",
                )
                
                await db.commit()
                logger.info(
                    "sicredi_boleto_baixa_already_liquidado_synced",
                    nosso_numero=nosso_numero,
                    admin_id=str(admin.id),
                )
            return {
                "status": "already_liquidado",
                "detail": "Boleto was already liquidated at Sicredi. Local status synchronized to LIQUIDADO.",
                "nosso_numero": nosso_numero,
            }
        
        # Handle 0078: título já baixado
        if exc.status_code == 422 and ("0078" in error_msg or "já baixado" in error_msg.lower()):
            stmt = select(Boleto).where(
                Boleto.nosso_numero == nosso_numero,
                Boleto.company_id == admin.company_id,
            )
            db_result = await db.execute(stmt)
            boleto_record = db_result.scalar_one_or_none()
            if boleto_record and boleto_record.status != BoletoStatus.CANCELADO:
                boleto_record.status = BoletoStatus.CANCELADO
                
                # Track manual action even when syncing already-baixado boleto
                boleto_record.writeoff_type = WriteoffType.MANUAL_ADMIN
                boleto_record.writeoff_by = admin.id
                boleto_record.writeoff_reason = "Tentativa de baixa manual - boleto já baixado no banco (sincronizado)"
                
                await log_audit(
                    db=db,
                    user_id=admin.id,
                    company_id=admin.company_id,
                    table_name="boletos",
                    operation="BAIXA_SYNC_BAIXADO",
                    resource_id=str(boleto_record.id),
                    detail=f"Boleto {nosso_numero} ja baixado no Sicredi. Sincronizado por admin.",
                )
                
                await db.commit()
                logger.info(
                    "sicredi_boleto_baixa_already_baixado_synced",
                    nosso_numero=nosso_numero,
                    admin_id=str(admin.id),
                )
            return {
                "status": "already_baixado",
                "detail": "Boleto was already cancelled (baixado) at Sicredi. Local status synchronized to CANCELADO.",
                "nosso_numero": nosso_numero,
            }
        
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.detail)

    # Auto-update local DB status + track manual baixa
    stmt = select(Boleto).where(
        Boleto.nosso_numero == nosso_numero,
        Boleto.company_id == admin.company_id,
    )
    db_result = await db.execute(stmt)
    boleto_record = db_result.scalar_one_or_none()
    if boleto_record:
        boleto_record.status = BoletoStatus.CANCELADO
        boleto_record.writeoff_type = WriteoffType.MANUAL_ADMIN
        boleto_record.writeoff_by = admin.id
        boleto_record.writeoff_reason = "Baixa manual via admin (cancelamento)"
        
        await log_audit(
            db=db,
            user_id=admin.id,
            company_id=admin.company_id,
            table_name="boletos",
            operation="BAIXA_MANUAL",
            resource_id=str(boleto_record.id),
            detail=f"Boleto {nosso_numero} cancelado manualmente pelo admin {admin.full_name or admin.email}",
        )
        
        await db.commit()
        logger.info(
            "sicredi_boleto_baixa_manual",
            nosso_numero=nosso_numero,
            admin_id=str(admin.id),
            boleto_id=str(boleto_record.id),
        )

    return {"status": "ok", "detail": "Boleto cancelled", "response": result}


@router.patch("/boletos/{nosso_numero}/negativacao")
async def negativar_boleto(
    nosso_numero: str,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_sicredi")),
):
    """Request negativation for an overdue boleto."""
    client = await sicredi_service.get_sicredi_client(db, admin.company_id)

    try:
        result = await client.boletos.negativar(nosso_numero)
        await sicredi_service.persist_token_cache(db, admin.company_id)
    except SicrediError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.detail)

    # Auto-update local DB status
    stmt = select(Boleto).where(
        Boleto.nosso_numero == nosso_numero,
        Boleto.company_id == admin.company_id,
    )
    db_result = await db.execute(stmt)
    boleto_record = db_result.scalar_one_or_none()
    if boleto_record:
        boleto_record.status = BoletoStatus.NEGATIVADO
        await db.commit()
        logger.info(f"Boleto {nosso_numero} local status updated to NEGATIVADO")

    return {"status": "ok", "detail": "Negativation requested", "response": result}


@router.patch("/boletos/{nosso_numero}/sustar-negativacao-baixar-titulo")
async def sustar_negativacao_baixar_boleto(
    nosso_numero: str,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_sicredi")),
):
    """Cancel negativation and simultaneously cancel (baixa) the boleto."""
    client = await sicredi_service.get_sicredi_client(db, admin.company_id)

    try:
        result = await client.boletos.sustar_negativacao_baixar(nosso_numero)
        await sicredi_service.persist_token_cache(db, admin.company_id)
    except SicrediError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.detail)

    # Auto-update local DB status
    stmt = select(Boleto).where(
        Boleto.nosso_numero == nosso_numero,
        Boleto.company_id == admin.company_id,
    )
    db_result = await db.execute(stmt)
    boleto_record = db_result.scalar_one_or_none()
    if boleto_record:
        boleto_record.status = BoletoStatus.CANCELADO
        await db.commit()
        logger.info(f"Boleto {nosso_numero} local status updated to CANCELADO (negativation cancelled + baixa)")

    return {"status": "ok", "detail": "Negativation cancelled and boleto baixado", "response": result}


@router.patch("/boletos/{nosso_numero}/data-vencimento")
async def alterar_vencimento(
    nosso_numero: str,
    payload: AlterarVencimentoAPIRequest,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_sicredi")),
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
    admin: Profile = Depends(require_permission("manage_sicredi")),
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
    admin: Profile = Depends(require_permission("manage_sicredi")),
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
    admin: Profile = Depends(require_permission("manage_sicredi")),
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
    admin: Profile = Depends(require_permission("manage_sicredi")),
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
    admin: Profile = Depends(require_permission("manage_sicredi")),
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
    admin: Profile = Depends(require_permission("manage_sicredi")),
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
    admin: Profile = Depends(require_permission("manage_sicredi")),
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
    admin: Profile = Depends(require_permission("manage_sicredi")),
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
