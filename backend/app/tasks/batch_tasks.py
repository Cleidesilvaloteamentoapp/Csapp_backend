"""Celery tasks for batch boleto creation and bulk operations."""

import asyncio
from datetime import date
from uuid import UUID

from dateutil.relativedelta import relativedelta

from app.tasks._async_helpers import TaskSessionFactory, run_in_task_loop
from app.tasks.celery_app import celery
from app.utils.logging import get_logger

logger = get_logger(__name__)

def _sicredi_or_none(value: str | None) -> str | None:
    """Return None for 'ISENTO' so the field is excluded from the Sicredi payload.

    The Sicredi API accepts VALOR or PERCENTUAL for juros/multa/desconto but
    rejects the string 'ISENTO' with HTTP 400. None → field omitted by
    `CriarBoletoRequest.to_api_payload()` (exclude_none=True).
    """
    if not value or value.upper() == "ISENTO":
        return None
    return value


def _fmt_num(value) -> str:
    """Format a numeric value for display, trimming trailing zeros (2 -> '2', 1.5 -> '1,5')."""
    try:
        d = float(value)
    except (TypeError, ValueError):
        return str(value)
    if d == int(d):
        return str(int(d))
    return f"{d:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _format_fee_instructions(input_data: dict) -> list[str]:
    """Build human-readable pt-BR instruction lines from the boleto fee fields.

    Mirrors the structured multa/juros/desconto values sent to Sicredi so the
    receiving bank teller and the payer see the same penalties in text form.
    Values equal to "ISENTO" (or missing) are skipped.
    """
    lines: list[str] = []

    tipo_multa = _sicredi_or_none(input_data.get("tipo_multa"))
    multa = input_data.get("multa")
    if tipo_multa and multa:
        if tipo_multa == "PERCENTUAL":
            lines.append(f"Após o vencimento, multa de {_fmt_num(multa)}%.")
        elif tipo_multa == "VALOR":
            lines.append(f"Após o vencimento, multa de R$ {_fmt_num(multa)}.")

    tipo_juros = _sicredi_or_none(input_data.get("tipo_juros"))
    juros = input_data.get("juros")
    if tipo_juros and juros:
        if tipo_juros == "PERCENTUAL_MES":
            lines.append(f"Juros de mora de {_fmt_num(juros)}% ao mês.")
        elif tipo_juros == "VALOR_DIA":
            lines.append(f"Juros de mora de R$ {_fmt_num(juros)} ao dia.")

    tipo_desconto = _sicredi_or_none(input_data.get("tipo_desconto"))
    valor_desconto = input_data.get("valor_desconto_1")
    if tipo_desconto and valor_desconto:
        lines.append(
            f"Desconto de R$ {_fmt_num(valor_desconto)} para pagamento até o vencimento."
        )

    return lines


def _clamp_negativacao(days: int | None) -> int | None:
    """Return None if days is outside the Sicredi-accepted range [3, 99]."""
    if days is None:
        return None
    try:
        d = int(days)
    except (TypeError, ValueError):
        return None
    return d if 3 <= d <= 99 else None


FREQUENCY_MONTHS = {
    "MENSAL": 1,
    "TRIMESTRAL": 3,
    "SEMESTRAL": 6,
    "ANUAL": 12,
}

ACTION_TO_BATCH_TYPE = {
    "BAIXA": "BATCH_BAIXA",
    "ALTERAR_VENCIMENTO": "BATCH_ALTERAR_VENCIMENTO",
    "ALTERAR_JUROS": "BATCH_ALTERAR_JUROS",
    "ALTERAR_DESCONTO": "BATCH_ALTERAR_DESCONTO",
    "CONCEDER_ABATIMENTO": "BATCH_CONCEDER_ABATIMENTO",
    "CANCELAR_ABATIMENTO": "BATCH_CANCELAR_ABATIMENTO",
    "NEGATIVACAO": "BATCH_NEGATIVACAO",
    "SUSTAR_NEGATIVACAO_BAIXAR": "BATCH_SUSTAR_NEGATIVACAO_BAIXAR",
}

STATUS_UPDATE_MAP = {
    "BAIXA": "CANCELADO",
    "NEGATIVACAO": "NEGATIVADO",
    "SUSTAR_NEGATIVACAO_BAIXAR": "CANCELADO",
}


# ---------------------------------------------------------------------------
# Batch Creation
# ---------------------------------------------------------------------------

async def _process_batch_creation_async(
    session_factory: TaskSessionFactory, batch_id: str, company_id: str
):
    """Create multiple boletos sequentially via Sicredi API."""
    from sqlalchemy import select
    from app.models.batch_operation import BatchOperation
    from app.models.boleto import Boleto
    from app.models.client import Client
    from app.models.enums import BoletoStatus
    from app.services import sicredi_service
    from app.services.sicredi.exceptions import SicrediError
    from app.services.sicredi.schemas import (
        BeneficiarioFinal,
        CriarBoletoRequest,
        Pagador,
    )

    async with session_factory() as db:
        # Load batch operation
        stmt = select(BatchOperation).where(BatchOperation.id == UUID(batch_id))
        result = await db.execute(stmt)
        batch = result.scalar_one_or_none()
        if not batch:
            logger.error("batch_not_found", batch_id=batch_id)
            return

        batch.status = "PROCESSING"
        await db.commit()

        input_data = batch.input_data or {}
        cid = UUID(company_id)

        # Get Sicredi client
        try:
            sicredi_client = await sicredi_service.get_sicredi_client(db, cid)
        except Exception as exc:
            batch.status = "FAILED"
            batch.error_summary = f"Failed to get Sicredi client: {str(exc)}"
            await db.commit()
            return

        # Verify client exists
        client_id = UUID(input_data["client_id"])
        stmt_c = select(Client).where(Client.id == client_id, Client.company_id == cid)
        res_c = await db.execute(stmt_c)
        client_record = res_c.scalar_one_or_none()
        if not client_record:
            batch.status = "FAILED"
            batch.error_summary = "Client not found"
            await db.commit()
            return

        # Calculate installment dates
        frequency = input_data.get("frequency", "MENSAL")
        duration_months = input_data.get("duration_months", 12)
        interval = FREQUENCY_MONTHS.get(frequency, 1)
        num_installments = duration_months // interval

        first_due = date.fromisoformat(input_data["data_primeiro_vencimento"])
        valor = float(input_data["valor"])

        batch.total_items = num_installments
        await db.commit()

        # Build pagador
        pagador_data = input_data.get("pagador", {})
        pagador = Pagador(
            tipoPessoa=pagador_data.get("tipo_pessoa", "PESSOA_FISICA"),
            documento=pagador_data.get("documento", ""),
            nome=pagador_data.get("nome", ""),
            endereco=pagador_data.get("endereco", ""),
            cidade=pagador_data.get("cidade", ""),
            uf=pagador_data.get("uf", ""),
            cep=pagador_data.get("cep", ""),
            email=pagador_data.get("email"),
            telefone=pagador_data.get("telefone"),
        )

        # Build beneficiario final if present
        beneficiario = None
        bf_data = input_data.get("beneficiario_final")
        if bf_data:
            beneficiario = BeneficiarioFinal(
                tipoPessoa=bf_data.get("tipo_pessoa", "PESSOA_FISICA"),
                documento=bf_data.get("documento", ""),
                nome=bf_data.get("nome", ""),
                logradouro=bf_data.get("logradouro", ""),
                numeroEndereco=bf_data.get("numero_endereco"),
                complemento=bf_data.get("complemento"),
                cidade=bf_data.get("cidade", ""),
                uf=bf_data.get("uf", ""),
                cep=bf_data.get("cep", 0),
                telefone=bf_data.get("telefone"),
            )

        # Build instruction lines describing the configured fees (multa/juros/desconto)
        # so the receiving bank and the payer see the penalties in text. Combine with
        # any user-provided lines, respecting Sicredi limits (mensagens: 4, informativos: 5).
        fee_lines = _format_fee_instructions(input_data)
        mensagens = ((input_data.get("mensagens") or []) + fee_lines)[:4]
        informativos = ((input_data.get("informativos") or []) + fee_lines)[:5]

        results = []

        for i in range(num_installments):
            due_date = first_due + relativedelta(months=interval * i)
            seu_numero = f"BAT{batch_id[-4:]}{i + 1:03d}"

            boleto_req = CriarBoletoRequest(
                tipoCobranca=input_data.get("tipo_cobranca", "HIBRIDO"),
                codigoBeneficiario=sicredi_client.credentials.codigo_beneficiario,
                pagador=pagador,
                especieDocumento=input_data.get(
                    "especie_documento", "DUPLICATA_MERCANTIL_INDICACAO"
                ),
                dataVencimento=due_date,
                valor=valor,
                seuNumero=seu_numero,
                beneficiarioFinal=beneficiario,
                tipoDesconto=_sicredi_or_none(input_data.get("tipo_desconto")),
                valorDesconto1=input_data.get("valor_desconto_1"),
                valorDesconto2=input_data.get("valor_desconto_2"),
                valorDesconto3=input_data.get("valor_desconto_3"),
                # Sicredi rejects "ISENTO" — only VALOR/PERCENTUAL are valid values.
                # When the user picks "Isento", the frontend omits the field; however
                # older batch records may have stored "ISENTO" in input_data. Filter it.
                tipoJuros=_sicredi_or_none(input_data.get("tipo_juros")),
                juros=input_data.get("juros"),
                tipoMulta=_sicredi_or_none(input_data.get("tipo_multa")),
                multa=input_data.get("multa"),
                descontoAntecipado=input_data.get("desconto_antecipado"),
                diasProtestoAuto=input_data.get("dias_protesto_auto"),
                # Sicredi requires 3-99 days; values outside that range cause 400.
                diasNegativacaoAuto=_clamp_negativacao(input_data.get("dias_negativacao_auto")),
                validadeAposVencimento=input_data.get("validade_apos_vencimento"),
                informativos=informativos or None,
                mensagens=mensagens or None,
            )

            try:
                api_result = await sicredi_client.boletos.criar(boleto_req)
                await sicredi_service.persist_token_cache(db, cid)

                # Persist boleto record
                boleto_record = Boleto(
                    company_id=cid,
                    client_id=client_id,
                    nosso_numero=api_result.nossoNumero,
                    seu_numero=seu_numero,
                    linha_digitavel=api_result.linhaDigitavel,
                    codigo_barras=api_result.codigoBarras,
                    tipo_cobranca=input_data.get("tipo_cobranca", "HIBRIDO"),
                    especie_documento=input_data.get(
                        "especie_documento", "DUPLICATA_MERCANTIL_INDICACAO"
                    ),
                    data_vencimento=due_date,
                    data_emissao=date.today(),
                    valor=valor,
                    status=BoletoStatus.NORMAL,
                    txid=api_result.txid,
                    qr_code=api_result.qrCode,
                    pagador_data=pagador_data,
                    raw_response=api_result.model_dump(mode="json"),
                    created_by=UUID(input_data["created_by"]) if input_data.get("created_by") else None,
                )
                db.add(boleto_record)
                await db.flush()

                results.append({
                    "index": i,
                    "nosso_numero": api_result.nossoNumero,
                    "seu_numero": seu_numero,
                    "status": "SUCCESS",
                    "detail": f"Boleto created, due {due_date.isoformat()}",
                    "boleto_id": str(boleto_record.id),
                })
                batch.completed_items += 1

            except SicrediError as exc:
                results.append({
                    "index": i,
                    "nosso_numero": None,
                    "seu_numero": seu_numero,
                    "status": "FAILED",
                    "detail": exc.detail or str(exc),
                    "boleto_id": None,
                })
                batch.failed_items += 1
                logger.warning(
                    "batch_create_item_failed",
                    batch_id=batch_id,
                    index=i,
                    error=exc.detail,
                )
            except Exception as exc:
                results.append({
                    "index": i,
                    "nosso_numero": None,
                    "seu_numero": seu_numero,
                    "status": "FAILED",
                    "detail": str(exc),
                    "boleto_id": None,
                })
                batch.failed_items += 1
                logger.warning(
                    "batch_create_item_error",
                    batch_id=batch_id,
                    index=i,
                    error=str(exc),
                )

            # Update progress
            batch.results = results
            await db.commit()

            # Rate limiting: 500ms between Sicredi API calls
            if i < num_installments - 1:
                await asyncio.sleep(0.5)

        # Final status
        if batch.failed_items == batch.total_items:
            batch.status = "FAILED"
            first_error = next(
                (r.get("detail") for r in results if r.get("status") == "FAILED"),
                "Unknown error",
            )
            batch.error_summary = (
                f"Todas as {batch.total_items} parcelas falharam ao registrar no Sicredi. "
                f"Primeiro erro: {first_error}"
            )
        else:
            batch.status = "COMPLETED"
            if batch.failed_items > 0:
                batch.error_summary = (
                    f"{batch.failed_items} de {batch.total_items} boletos falharam no Sicredi"
                )

        batch.results = results
        await db.commit()
        logger.info(
            "batch_creation_completed",
            batch_id=batch_id,
            total=batch.total_items,
            completed=batch.completed_items,
            failed=batch.failed_items,
        )


@celery.task(bind=True, max_retries=1, default_retry_delay=60)
def process_batch_creation(self, batch_id: str, company_id: str):
    """Celery task: create multiple boletos in batch via Sicredi API."""
    try:
        run_in_task_loop(
            lambda sf: _process_batch_creation_async(sf, batch_id, company_id)
        )
    except Exception as exc:
        logger.error("batch_creation_task_failed", batch_id=batch_id, error=str(exc))
        # Mark batch as failed
        try:
            run_in_task_loop(
                lambda sf: _mark_batch_failed(sf, batch_id, str(exc))
            )
        except Exception:
            pass
        self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Batch Operations (bulk actions on existing boletos)
# ---------------------------------------------------------------------------

async def _process_batch_operation_async(
    session_factory: TaskSessionFactory, batch_id: str, company_id: str
):
    """Execute a bulk action on multiple boletos sequentially."""
    from sqlalchemy import select
    from app.models.batch_operation import BatchOperation
    from app.models.boleto import Boleto
    from app.models.enums import BoletoStatus
    from app.services import sicredi_service
    from app.services.sicredi.exceptions import SicrediError
    from app.services.sicredi.schemas import (
        AlterarDescontoRequest,
        AlterarJurosRequest,
        AlterarVencimentoRequest,
        ConcederAbatimentoRequest,
    )

    async with session_factory() as db:
        stmt = select(BatchOperation).where(BatchOperation.id == UUID(batch_id))
        result = await db.execute(stmt)
        batch = result.scalar_one_or_none()
        if not batch:
            logger.error("batch_not_found", batch_id=batch_id)
            return

        batch.status = "PROCESSING"
        await db.commit()

        input_data = batch.input_data or {}
        cid = UUID(company_id)
        action = input_data.get("action", "")
        nosso_numeros = input_data.get("nosso_numeros", [])

        try:
            sicredi_client = await sicredi_service.get_sicredi_client(db, cid)
        except Exception as exc:
            batch.status = "FAILED"
            batch.error_summary = f"Failed to get Sicredi client: {str(exc)}"
            await db.commit()
            return

        results = []

        for i, nn in enumerate(nosso_numeros):
            try:
                api_result = await _execute_action(
                    sicredi_client, action, nn, input_data
                )
                await sicredi_service.persist_token_cache(db, cid)

                # Auto-update local DB status if applicable
                new_status = STATUS_UPDATE_MAP.get(action)
                if new_status:
                    stmt_b = select(Boleto).where(
                        Boleto.nosso_numero == nn,
                        Boleto.company_id == cid,
                    )
                    res_b = await db.execute(stmt_b)
                    boleto_record = res_b.scalar_one_or_none()
                    if boleto_record:
                        boleto_record.status = BoletoStatus(new_status)

                results.append({
                    "index": i,
                    "nosso_numero": nn,
                    "status": "SUCCESS",
                    "detail": f"{action} executed successfully",
                    "boleto_id": None,
                })
                batch.completed_items += 1

            except SicrediError as exc:
                results.append({
                    "index": i,
                    "nosso_numero": nn,
                    "status": "FAILED",
                    "detail": exc.detail or str(exc),
                    "boleto_id": None,
                })
                batch.failed_items += 1
                logger.warning(
                    "batch_op_item_failed",
                    batch_id=batch_id,
                    nn=nn,
                    action=action,
                    error=exc.detail,
                )
            except Exception as exc:
                results.append({
                    "index": i,
                    "nosso_numero": nn,
                    "status": "FAILED",
                    "detail": str(exc),
                    "boleto_id": None,
                })
                batch.failed_items += 1
                logger.warning(
                    "batch_op_item_error",
                    batch_id=batch_id,
                    nn=nn,
                    action=action,
                    error=str(exc),
                )

            batch.results = results
            await db.commit()

            # Rate limiting: 500ms between Sicredi API calls
            if i < len(nosso_numeros) - 1:
                await asyncio.sleep(0.5)

        # Final status
        if batch.failed_items == batch.total_items:
            batch.status = "FAILED"
            batch.error_summary = "All items failed"
        else:
            batch.status = "COMPLETED"
            if batch.failed_items > 0:
                batch.error_summary = f"{batch.failed_items} of {batch.total_items} items failed"

        batch.results = results
        await db.commit()
        logger.info(
            "batch_operation_completed",
            batch_id=batch_id,
            action=action,
            total=batch.total_items,
            completed=batch.completed_items,
            failed=batch.failed_items,
        )


async def _execute_action(sicredi_client, action: str, nosso_numero: str, input_data: dict):
    """Dispatch the correct Sicredi service method based on action type."""
    from app.services.sicredi.schemas import (
        AlterarDescontoRequest,
        AlterarJurosRequest,
        AlterarVencimentoRequest,
        ConcederAbatimentoRequest,
    )

    if action == "BAIXA":
        return await sicredi_client.boletos.baixar(nosso_numero)

    elif action == "ALTERAR_VENCIMENTO":
        return await sicredi_client.boletos.alterar_vencimento(
            nosso_numero,
            AlterarVencimentoRequest(
                dataVencimento=date.fromisoformat(input_data["data_vencimento"])
            ),
        )

    elif action == "ALTERAR_JUROS":
        return await sicredi_client.boletos.alterar_juros(
            nosso_numero,
            AlterarJurosRequest(valorOuPercentual=input_data["valor_ou_percentual"]),
        )

    elif action == "ALTERAR_DESCONTO":
        return await sicredi_client.boletos.alterar_desconto(
            nosso_numero,
            AlterarDescontoRequest(
                valorDesconto1=input_data.get("valor_desconto_1"),
                valorDesconto2=input_data.get("valor_desconto_2"),
                valorDesconto3=input_data.get("valor_desconto_3"),
            ),
        )

    elif action == "CONCEDER_ABATIMENTO":
        return await sicredi_client.boletos.conceder_abatimento(
            nosso_numero,
            ConcederAbatimentoRequest(valorAbatimento=input_data["valor_abatimento"]),
        )

    elif action == "CANCELAR_ABATIMENTO":
        return await sicredi_client.boletos.cancelar_abatimento(nosso_numero)

    elif action == "NEGATIVACAO":
        return await sicredi_client.boletos.negativar(nosso_numero)

    elif action == "SUSTAR_NEGATIVACAO_BAIXAR":
        return await sicredi_client.boletos.sustar_negativacao_baixar(nosso_numero)

    else:
        raise ValueError(f"Unknown action: {action}")


async def _mark_batch_failed(
    session_factory: TaskSessionFactory, batch_id: str, error: str
):
    """Mark a batch operation as failed (used by retry handler)."""
    from sqlalchemy import select
    from app.models.batch_operation import BatchOperation

    async with session_factory() as db:
        stmt = select(BatchOperation).where(BatchOperation.id == UUID(batch_id))
        result = await db.execute(stmt)
        batch = result.scalar_one_or_none()
        if batch:
            batch.status = "FAILED"
            batch.error_summary = error
            await db.commit()


@celery.task(bind=True, max_retries=1, default_retry_delay=60)
def process_batch_operation(self, batch_id: str, company_id: str):
    """Celery task: execute a bulk action on multiple boletos."""
    try:
        run_in_task_loop(
            lambda sf: _process_batch_operation_async(sf, batch_id, company_id)
        )
    except Exception as exc:
        logger.error("batch_operation_task_failed", batch_id=batch_id, error=str(exc))
        try:
            run_in_task_loop(
                lambda sf: _mark_batch_failed(sf, batch_id, str(exc))
            )
        except Exception:
            pass
        self.retry(exc=exc)
