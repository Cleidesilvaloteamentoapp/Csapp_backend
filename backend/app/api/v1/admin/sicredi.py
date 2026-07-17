
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

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_company_admin, require_permission
from app.models.user import Profile
from app.models.client import Client
from app.models.boleto import Boleto
from app.models.enums import ClientStatus, BoletoStatus, InvoiceStatus, NotificationType, WriteoffType, BoletoTag
from app.models.invoice import Invoice
from app.services.admin_notify_service import notify_admins
from app.services.notification_settings_service import get_or_create as get_notif_settings
from sqlalchemy import select
from datetime import date as dt_date, datetime, timedelta, timezone
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
from app.services.boleto_status_service import mark_boleto_liquidado
from app.services.sicredi.exceptions import SicrediError
from app.services.sicredi_audit_service import DIRECTION_OUTBOUND, log_sicredi_event
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
from app.core.database import async_session_factory
from app.services.sicredi.audit_recorder import (
    persist_recorded_calls,
    start_recording,
    stop_recording,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def sicredi_audit_trail():
    """Router-wide dependency: record every outbound Sicredi call made while
    handling the request and persist them as OUTBOUND sicredi_events.

    Uses its own DB session so the audit rows survive even when the endpoint
    raises (get_db rolls back its session on error) — which is exactly the case
    that previously left the audit trail empty for failed calls.
    """
    token = start_recording()
    try:
        yield
    finally:
        calls = stop_recording(token)
        if not calls:
            return
        try:
            async with async_session_factory() as audit_db:
                await persist_recorded_calls(audit_db, calls)
                await audit_db.commit()
        except Exception as exc:  # auditing must never break the response
            logger.warning("sicredi_audit_trail_persist_failed", error=str(exc))


router = APIRouter(
    prefix="/sicredi",
    tags=["Admin Sicredi"],
    dependencies=[Depends(sicredi_audit_trail)],
)


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
        # 'ISENTO' is not a valid Sicredi value; omit the field entirely.
        tipoJuros=payload.tipo_juros if payload.tipo_juros and payload.tipo_juros.upper() != "ISENTO" else None,
        juros=payload.juros,
        tipoMulta=payload.tipo_multa if payload.tipo_multa and payload.tipo_multa.upper() != "ISENTO" else None,
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

    # Notify client (WhatsApp + in-app) and admin
    try:
        notif_settings = await get_notif_settings(db, admin.company_id)
        portal_url = f"{settings.FRONTEND_URL}/cliente/boletos"

        if notif_settings.notify_client_new_boleto and client_record.phone:
            from app.services.whatsapp_service import notify_new_boleto
            await notify_new_boleto(
                to=client_record.phone,
                name=client_record.full_name,
                due_date=payload.data_vencimento.isoformat(),
                amount=str(payload.valor),
                linha_digitavel=result.linhaDigitavel or "",
                portal_url=portal_url,
                db=db,
                company_id=admin.company_id,
            )

        if notif_settings.notify_client_new_boleto and client_record.profile_id:
            from app.services.notification_service import notify_boleto_emitido
            from app.models.user import Profile as _Profile
            profile = (await db.execute(
                select(_Profile).where(_Profile.id == client_record.profile_id)
            )).scalar_one_or_none()
            if profile:
                await notify_boleto_emitido(
                    db,
                    company_id=admin.company_id,
                    user_id=profile.id,
                    nosso_numero=boleto_record.nosso_numero or "",
                    valor=str(payload.valor),
                    data_vencimento=payload.data_vencimento.isoformat(),
                )

        await notify_admins(
            db,
            admin.company_id,
            "notify_admin_boleto_generated",
            title="Novo boleto gerado",
            message=f"Boleto {boleto_record.nosso_numero} gerado para {client_record.full_name} | R$ {payload.valor} | Venc. {payload.data_vencimento}.",
            n_type=NotificationType.BOLETO_EMITIDO,
            data={"nosso_numero": boleto_record.nosso_numero, "client_id": str(client_record.id)},
        )
    except Exception as exc:
        logger.warning("boleto_notification_failed", nosso_numero=boleto_record.nosso_numero, error=str(exc))

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

    # Verify Sicredi credentials are configured for this company.
    # Without this, the batch would be enqueued, fail silently in the worker,
    # and leave the user thinking boletos are "stuck saving to DB only".
    from app.services.sicredi_service import get_credential
    cred = await get_credential(db, admin.company_id)
    if not cred:
        raise HTTPException(
            status_code=400,
            detail=(
                "Credenciais Sicredi não cadastradas para esta empresa. "
                "Cadastre via POST /admin/sicredi/credentials antes de gerar boletos."
            ),
        )

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


@router.get("/boletos/batch/{batch_id}/carne-pdf")
async def baixar_carne_batch(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_sicredi")),
):
    """Download every boleto created in a batch as a single multi-page PDF (carnê).

    Fetches each boleto's PDF from Sicredi (using the stored linhaDigitavel) and
    concatenates them into one file, ordered by due date, to ease sending to the client.
    """
    import asyncio
    import io
    from uuid import UUID as _UUID

    from pypdf import PdfReader, PdfWriter

    stmt = select(BatchOperation).where(
        BatchOperation.id == _UUID(batch_id),
        BatchOperation.company_id == admin.company_id,
    )
    result = await db.execute(stmt)
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch operation not found")

    # Collect the boleto ids that were created successfully
    boleto_ids = [
        _UUID(r["boleto_id"])
        for r in (batch.results or [])
        if r.get("status") == "SUCCESS" and r.get("boleto_id")
    ]
    if not boleto_ids:
        raise HTTPException(
            status_code=404,
            detail="Nenhum boleto gerado com sucesso neste lote para montar o carnê.",
        )

    stmt_b = (
        select(Boleto)
        .where(Boleto.id.in_(boleto_ids), Boleto.company_id == admin.company_id)
        .order_by(Boleto.data_vencimento.asc())
    )
    res_b = await db.execute(stmt_b)
    boletos = [b for b in res_b.scalars().all() if b.linha_digitavel]
    if not boletos:
        raise HTTPException(
            status_code=422,
            detail="Boletos do lote não possuem linha digitável para gerar o PDF.",
        )

    client = await sicredi_service.get_sicredi_client(db, admin.company_id)

    writer = PdfWriter()
    try:
        for idx, boleto in enumerate(boletos):
            pdf_bytes = await client.boletos.gerar_pdf(boleto.linha_digitavel)
            reader = PdfReader(io.BytesIO(pdf_bytes))
            for page in reader.pages:
                writer.add_page(page)
            # Rate limiting: 500ms between Sicredi API calls
            if idx < len(boletos) - 1:
                await asyncio.sleep(0.5)
        await sicredi_service.persist_token_cache(db, admin.company_id)
    except SicrediError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.detail)

    output = io.BytesIO()
    writer.write(output)

    return Response(
        content=output.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=carne_{batch_id}.pdf"},
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
        # Record unknown situações so the mapping gap is visible in the audit trail
        # instead of silently doing nothing.
        await log_sicredi_event(
            db,
            direction=DIRECTION_OUTBOUND,
            event_type="UNKNOWN_SITUACAO",
            company_id=admin.company_id,
            nosso_numero=nosso_numero,
            success=True,
            payload=sicredi_data.model_dump(mode="json"),
        )
        await db.commit()
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

    if new_status == BoletoStatus.LIQUIDADO:
        await mark_boleto_liquidado(db, boleto_record, source="manual_sync")
    else:
        boleto_record.status = new_status
        # Track external baixa - only mark if not already tracked as manual
        if is_baixa_externa and previous_writeoff_type != WriteoffType.MANUAL_ADMIN:
            boleto_record.writeoff_type = WriteoffType.BAIXA_EXTERNA
            boleto_record.writeoff_reason = f"Baixa externa via Sicredi (situacao: {sicredi_data.situacao}). Sincronizado via endpoint /sync."

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


# ---------------------------------------------------------------------------
# Integration health / diagnostics
# ---------------------------------------------------------------------------

@router.get("/integration-health")
async def integration_health(
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_sicredi")),
):
    """Snapshot of the Sicredi integration health for the admin's company.

    Surfaces the webhook contract status at Sicredi, when the last webhook /
    reconciliation happened, and open-boleto counts — so a stalled beat/worker or
    a missing webhook contract (the usual causes of "paid but not updated") are
    visible instead of silent.
    """
    from sqlalchemy import func
    from app.models.sicredi_event import SicrediEvent

    company_filter = SicrediEvent.company_id == admin.company_id

    # Webhook contract at Sicredi (best-effort — never fail the whole endpoint).
    webhook_contract = None
    try:
        client = await sicredi_service.get_sicredi_client(db, admin.company_id)
        contracts = await client.webhooks.consultar_contratos()
        await sicredi_service.persist_token_cache(db, admin.company_id)
        webhook_contract = {"status": "ok", "data": contracts}
    except SicrediError as exc:
        webhook_contract = {"status": "error", "detail": str(exc.detail or exc)}
    except Exception as exc:
        webhook_contract = {"status": "error", "detail": str(exc)}

    async def _last_event_at(*event_types: str):
        stmt = select(SicrediEvent.created_at).where(company_filter)
        if event_types:
            stmt = stmt.where(SicrediEvent.event_type.in_(event_types))
        stmt = stmt.order_by(SicrediEvent.created_at.desc()).limit(1)
        return (await db.execute(stmt)).scalar_one_or_none()

    last_webhook_at = (
        await db.execute(
            select(SicrediEvent.created_at)
            .where(company_filter, SicrediEvent.direction == "INBOUND")
            .order_by(SicrediEvent.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    last_sync_at = await _last_event_at("SYNC_RUN")
    last_reconcile_at = await _last_event_at("SYNC_LIQUIDADOS_DIA")

    open_boletos = (
        await db.execute(
            select(func.count())
            .select_from(Boleto)
            .where(
                Boleto.company_id == admin.company_id,
                Boleto.status.in_([BoletoStatus.NORMAL, BoletoStatus.VENCIDO]),
            )
        )
    ).scalar_one()

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    events_last_24h = (
        await db.execute(
            select(func.count())
            .select_from(SicrediEvent)
            .where(company_filter, SicrediEvent.created_at >= since)
        )
    ).scalar_one()

    return {
        "webhook_contract": webhook_contract,
        "last_webhook_received_at": last_webhook_at,
        "last_sync_run_at": last_sync_at,
        "last_reconcile_at": last_reconcile_at,
        "open_boletos": open_boletos,
        "events_last_24h": events_last_24h,
    }
