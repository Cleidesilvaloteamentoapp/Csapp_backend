"""Celery tasks for batch boleto creation and bulk operations."""

import asyncio
from datetime import date
from uuid import UUID

from dateutil.relativedelta import relativedelta

from app.services.sicredi.fees import DAYS_PER_MONTH
from app.tasks._async_helpers import TaskSessionFactory, run_in_task_loop
from app.tasks.celery_app import celery
from app.utils.logging import get_logger

logger = get_logger(__name__)

def _fee_type_or_none(value: str | None) -> str | None:
    """Return None for 'ISENTO'/empty so the fee is treated as not applicable.

    Only used to decide whether to render an instruction line — the outbound
    payload is normalized by `CriarBoletoRequest` (app.services.sicredi.fees).
    """
    if not value or value.strip().upper() == "ISENTO":
        return None
    return value.strip().upper()


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

    tipo_multa = _fee_type_or_none(input_data.get("tipo_multa"))
    multa = input_data.get("multa")
    if tipo_multa and multa:
        if tipo_multa == "PERCENTUAL":
            lines.append(f"Após o vencimento, multa de {_fmt_num(multa)}%.")
        elif tipo_multa == "VALOR":
            lines.append(f"Após o vencimento, multa de R$ {_fmt_num(multa)}.")

    # The payer reads the contract's own wording: a contract states "0,33% ao
    # dia" even though Sicredi registers the monthly equivalent (9,90% ao mês).
    tipo_juros = _fee_type_or_none(input_data.get("tipo_juros"))
    juros = input_data.get("juros")
    if tipo_juros and juros:
        if tipo_juros == "PERCENTUAL_DIA":
            lines.append(f"Juros de mora de {_fmt_num(juros)}% ao dia.")
        elif tipo_juros in ("PERCENTUAL_MES", "PERCENTUAL"):
            lines.append(f"Juros de mora de {_fmt_num(juros)}% ao mês.")
        elif tipo_juros in ("VALOR_DIA", "VALOR"):
            lines.append(f"Juros de mora de R$ {_fmt_num(juros)} ao dia.")

    tipo_desconto = _fee_type_or_none(input_data.get("tipo_desconto"))
    valor_desconto = input_data.get("valor_desconto_1")
    if tipo_desconto and valor_desconto:
        lines.append(
            f"Desconto de R$ {_fmt_num(valor_desconto)} para pagamento até o vencimento."
        )

    return lines


def _format_fee_lines_from_rates(penalty_rate, daily_interest_rate) -> list[str]:
    """Build fee instruction lines from stored fractional rates (0.02 -> 2%).

    Used as a fallback when the batch didn't carry explicit multa/juros: the
    company's configured rates (cadastro / financial settings) still inform the
    payer and the receiving bank of the late-fee policy. The daily interest is
    expressed per month (rate * 30) to match how boletos usually state it.
    """
    lines: list[str] = []
    try:
        p = float(penalty_rate) if penalty_rate is not None else 0.0
    except (TypeError, ValueError):
        p = 0.0
    try:
        d = float(daily_interest_rate) if daily_interest_rate is not None else 0.0
    except (TypeError, ValueError):
        d = 0.0

    if p > 0:
        lines.append(f"Após o vencimento, multa de {_fmt_num(p * 100)}%.")
    if d > 0:
        lines.append(f"Juros de mora de {_fmt_num(d * float(DAYS_PER_MONTH) * 100)}% ao mês.")
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

async def _resolve_invoice_ids(
    db,
    company_id: UUID,
    client_id: UUID,
    client_lot_id: UUID | None,
    due_dates: list[date],
) -> list[UUID | None]:
    """Map each installment of a batch to the Invoice it bills, by position.

    Binding the boleto to its invoice is what makes the whole renewal chain work:
    settlement flips the Invoice to PAID, and the cycle-completion job counts
    those PAID invoices to decide when to raise a CycleApproval. A batch that
    leaves `invoice_id` NULL produces boletos that can never release a cycle.

    Returns a list aligned with *due_dates*; an entry is None when no unbilled
    invoice matches, so the boleto is still issued rather than silently dropped.
    """
    from sqlalchemy import select
    from app.models.boleto import Boleto
    from app.models.client_lot import ClientLot
    from app.models.enums import InvoiceStatus
    from app.models.invoice import Invoice

    stmt = (
        select(Invoice)
        .where(
            Invoice.company_id == company_id,
            Invoice.status.in_([InvoiceStatus.PENDING, InvoiceStatus.OVERDUE]),
        )
        .order_by(Invoice.due_date.asc(), Invoice.installment_number.asc())
    )
    if client_lot_id is not None:
        stmt = stmt.where(Invoice.client_lot_id == client_lot_id)
    else:
        # Legacy batches carry only a client: consider every contract they hold.
        stmt = stmt.where(
            Invoice.client_lot_id.in_(
                select(ClientLot.id).where(ClientLot.client_id == client_id)
            )
        )

    candidates = list((await db.execute(stmt)).scalars().all())
    if not candidates:
        return [None] * len(due_dates)

    # Never bind an invoice that already carries a live boleto, or the same
    # installment would be charged twice.
    taken = {
        row[0]
        for row in (
            await db.execute(
                select(Boleto.invoice_id).where(
                    Boleto.invoice_id.in_([inv.id for inv in candidates])
                )
            )
        ).all()
        if row[0] is not None
    }
    available = [inv for inv in candidates if inv.id not in taken]

    by_due: dict[date, list] = {}
    for inv in available:
        by_due.setdefault(inv.due_date, []).append(inv)

    resolved: list[UUID | None] = []
    used: set[UUID] = set()
    for due in due_dates:
        exact = next((i for i in by_due.get(due, []) if i.id not in used), None)
        if exact is None:
            # Fall back to the earliest still-unused invoice: the batch due dates
            # are derived from a frequency, so they drift from the contract's own
            # schedule, but the order of installments is the same.
            exact = next((i for i in available if i.id not in used), None)
        if exact is None:
            resolved.append(None)
            continue
        used.add(exact.id)
        resolved.append(exact.id)

    return resolved


async def _process_batch_creation_async(
    session_factory: TaskSessionFactory, batch_id: str, company_id: str
):
    """Create multiple boletos sequentially via Sicredi API."""
    from sqlalchemy import select
    from app.models.batch_operation import BatchOperation
    from app.models.boleto import Boleto
    from app.models.client import Client
    from app.models.enums import BoletoStatus, BoletoTag
    from app.services import sicredi_service
    from app.services.sicredi.audit_recorder import (
        persist_recorded_calls,
        start_recording,
        stop_recording,
    )
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

        # Record every outbound Sicredi call for the audit trail.
        audit_token = start_recording()

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
        if not fee_lines:
            # The batch carried no explicit multa/juros: fall back to the company's
            # configured financial settings (cadastro) so the boleto still informs
            # the late-fee policy. Mirrors the rates used for segunda-via correction.
            from app.services.financial_defaults_service import (
                HARDCODED_DAILY_INTEREST_RATE,
                HARDCODED_PENALTY_RATE,
                get_company_settings,
            )

            cfs = await get_company_settings(db, cid)
            penalty = (
                cfs.penalty_rate
                if cfs and cfs.penalty_rate is not None
                else HARDCODED_PENALTY_RATE
            )
            daily = (
                cfs.daily_interest_rate
                if cfs and cfs.daily_interest_rate is not None
                else HARDCODED_DAILY_INTEREST_RATE
            )
            fee_lines = _format_fee_lines_from_rates(penalty, daily)
        mensagens = ((input_data.get("mensagens") or []) + fee_lines)[:4]
        informativos = ((input_data.get("informativos") or []) + fee_lines)[:5]

        # Bind each installment to the Invoice it bills before issuing anything:
        # a boleto with a NULL invoice_id can never settle its installment, and
        # the cycle-renewal chain is driven entirely off settled invoices.
        due_dates = [
            first_due + relativedelta(months=interval * i) for i in range(num_installments)
        ]
        raw_lot_id = input_data.get("client_lot_id")
        client_lot_id = UUID(raw_lot_id) if raw_lot_id else None
        invoice_ids = await _resolve_invoice_ids(
            db, cid, client_id, client_lot_id, due_dates
        )
        unbound = sum(1 for inv_id in invoice_ids if inv_id is None)
        if unbound:
            logger.warning(
                "batch_create_unbound_installments",
                batch_id=batch_id,
                unbound=unbound,
                total=num_installments,
                client_lot_id=str(client_lot_id) if client_lot_id else None,
            )

        results = []
        aborted_detail: str | None = None

        for i in range(num_installments):
            due_date = due_dates[i]
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
                # Fee types are translated to Sicredi's VALOR/PERCENTUAL vocabulary
                # by CriarBoletoRequest itself (app.services.sicredi.fees), which
                # also drops an amount whose type turned out to be exempt.
                tipoDesconto=input_data.get("tipo_desconto"),
                valorDesconto1=input_data.get("valor_desconto_1"),
                valorDesconto2=input_data.get("valor_desconto_2"),
                valorDesconto3=input_data.get("valor_desconto_3"),
                tipoJuros=input_data.get("tipo_juros"),
                juros=input_data.get("juros"),
                tipoMulta=input_data.get("tipo_multa"),
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
                    invoice_id=invoice_ids[i],
                    tag=BoletoTag.PARCELA_CONTRATO,
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
                # A payload Sicredi refuses will be refused identically by every
                # remaining installment — they share everything but the due date.
                # Stop instead of burning N-1 calls (and N-1 rate-limit sleeps)
                # on the same rejection, so the error stays legible.
                if i == 0 and exc.status_code in (400, 422) and num_installments > 1:
                    aborted_detail = exc.detail or str(exc)
                    logger.warning(
                        "batch_create_aborted_invalid_payload",
                        batch_id=batch_id,
                        remaining=num_installments - (i + 1),
                        error=aborted_detail,
                    )
                    batch.results = results
                    await db.commit()
                    break
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
        if aborted_detail:
            batch.status = "FAILED"
            batch.error_summary = (
                f"O Sicredi recusou a 1ª parcela e as {batch.total_items - 1} restantes "
                f"não foram enviadas, pois usariam os mesmos dados. "
                f"Nenhum boleto foi registrado. Erro: {aborted_detail}"
            )
        elif batch.failed_items == batch.total_items:
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

        # Persist the outbound Sicredi calls made during this batch.
        try:
            await persist_recorded_calls(db, stop_recording(audit_token))
            await db.commit()
        except Exception as exc:
            logger.warning("batch_creation_audit_failed", batch_id=batch_id, error=str(exc))

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
    from app.services.sicredi.audit_recorder import (
        persist_recorded_calls,
        start_recording,
        stop_recording,
    )
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

        # Record every outbound Sicredi call for the audit trail.
        audit_token = start_recording()

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

        # Persist the outbound Sicredi calls made during this batch.
        try:
            await persist_recorded_calls(db, stop_recording(audit_token))
            await db.commit()
        except Exception as exc:
            logger.warning("batch_operation_audit_failed", batch_id=batch_id, error=str(exc))

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
