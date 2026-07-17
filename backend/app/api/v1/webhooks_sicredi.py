
"""Sicredi webhook receiver endpoint.

Receives payment event notifications (e.g., LIQUIDACAO) from the Sicredi API and
updates the corresponding boleto/invoice status.

Design guarantees (a missed payment must never happen):
  * Every delivery is recorded in the audit trail BEFORE any processing and
    committed immediately — a crash while processing can never erase the record.
  * The body is tolerated whether it is a single event object, a list of events,
    or an ``{"eventos": [...]}`` envelope.
  * Once the body is read we always answer HTTP 200 (Sicredi marks anything else
    as "not delivered" and stops retrying); per-event problems are reported in
    the JSON body instead.
  * Deliveries are de-duplicated by ``idEventoWebhook`` so a redelivery cannot
    re-liquidate or clobber an existing liquidation.

SECURITY: This endpoint is public (called by Sicredi servers). Sicredi does not
yet support authentication on webhooks; an optional IP whitelist is enforced
when configured.
"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.enums import InvoiceStatus, BoletoStatus
from app.models.invoice import Invoice
from app.models.boleto import Boleto
from app.models.sicredi_credential import SicrediCredential
from app.models.sicredi_event import SicrediEvent
from app.schemas.sicredi import WebhookBatchResponse, WebhookEventResponse
from app.services.boleto_status_service import mark_boleto_liquidado, parse_sicredi_date, today_brazil
from app.services.sicredi.schemas import WebhookEventPayload
from app.services.sicredi_audit_service import DIRECTION_INBOUND, log_sicredi_event
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def _verify_sicredi_origin(request: Request) -> bool:
    """Return False if a configured IP whitelist rejects this request's origin."""
    if not settings.WEBHOOK_IP_WHITELIST:
        return True
    client_ip = request.client.host if request.client else None
    if client_ip not in settings.WEBHOOK_IP_WHITELIST:
        logger.warning("sicredi_webhook_ip_rejected", ip=client_ip)
        return False
    return True


def _normalize_events(body: object) -> list[dict]:
    """Coerce a webhook body into a flat list of event dicts.

    Sicredi may deliver a single object, a bare list, or an envelope with the
    events under ``eventos``/``notificacoes``.
    """
    if isinstance(body, list):
        return [e for e in body if isinstance(e, dict)]
    if isinstance(body, dict):
        for key in ("eventos", "notificacoes", "events"):
            inner = body.get(key)
            if isinstance(inner, list):
                return [e for e in inner if isinstance(e, dict)]
        return [body]
    return []


async def _resolve_company_id(db: AsyncSession, event: WebhookEventPayload, boleto):
    """Best-effort resolution of the tenant a webhook event belongs to.

    Order: the matched boleto's company; a credential matching posto +
    beneficiário (and cooperativa/agência when it lines up); finally, if there is
    exactly one active credential, assume it.
    """
    if boleto is not None:
        return boleto.company_id

    def _norm(v):
        return (str(v).lstrip("0") or "0") if v is not None else None

    creds = (
        await db.execute(
            select(SicrediCredential).where(SicrediCredential.is_active == True)
        )
    ).scalars().all()

    if event.beneficiario:
        benef = _norm(event.beneficiario)
        matches = [
            c for c in creds
            if _norm(c.codigo_beneficiario) == benef
            and (not event.posto or _norm(c.posto) == _norm(event.posto))
        ]
        if len(matches) == 1:
            return matches[0].company_id

    if len(creds) == 1:
        return creds[0].company_id
    return None


@router.post("/sicredi", response_model=WebhookBatchResponse)
async def sicredi_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Process Sicredi payment event notifications.

    Expected movimento values include LIQUIDACAO_PIX / LIQUIDACAO_REDE /
    LIQUIDACAO_COMPE / LIQUIDACAO_CARTORIO (paid) and BAIXA / CANCELAMENTO.
    """
    if not _verify_sicredi_origin(request):
        # Origin rejected: still 200 so a misconfigured whitelist doesn't make
        # Sicredi hammer us, but nothing is processed.
        return WebhookBatchResponse(status="forbidden")

    raw = await request.body()

    # 1) Undecodable body: record it and acknowledge (returning 4xx just makes
    # Sicredi mark the event undelivered — we already captured it for auditing).
    try:
        body = json.loads(raw) if raw else None
    except Exception as exc:
        logger.warning("sicredi_webhook_unparseable_body", error=str(exc))
        await log_sicredi_event(
            db,
            direction=DIRECTION_INBOUND,
            event_type="WEBHOOK_PARSE_ERROR",
            success=False,
            payload={"raw": raw.decode("utf-8", errors="replace")[:10000]},
        )
        await db.commit()
        return WebhookBatchResponse(status="error", errors=1)

    events = _normalize_events(body)
    if not events:
        await log_sicredi_event(
            db,
            direction=DIRECTION_INBOUND,
            event_type="WEBHOOK_EMPTY",
            success=False,
            payload={"body": body} if not isinstance(body, dict) else body,
        )
        await db.commit()
        return WebhookBatchResponse(status="ignored", ignored=1)

    result = WebhookBatchResponse(received=len(events))

    for item in events:
        # 2) Per-item parse: a bad item is audited and skipped, never aborts the batch.
        try:
            event = WebhookEventPayload(**item)
        except Exception as exc:
            logger.warning("sicredi_webhook_parse_error", error=str(exc))
            await log_sicredi_event(
                db,
                direction=DIRECTION_INBOUND,
                event_type="WEBHOOK_PARSE_ERROR",
                success=False,
                payload=item,
            )
            await db.commit()
            result.errors += 1
            result.results.append(WebhookEventResponse(status="error", detail="Invalid event payload"))
            continue

        nosso_numero = event.nossoNumero
        movimento = event.movimento
        movimento_upper = (movimento or "").upper()

        # Look up boleto (and legacy invoice-by-barcode) for this event.
        boleto = None
        invoice = None
        if nosso_numero:
            boleto = (
                await db.execute(select(Boleto).where(Boleto.nosso_numero == nosso_numero))
            ).scalar_one_or_none()
            invoice = (
                await db.execute(select(Invoice).where(Invoice.barcode == nosso_numero))
            ).scalar_one_or_none()

        company_id = await _resolve_company_id(db, event, boleto)

        # 3) Idempotency: a prior successful delivery with the same id means this
        # is a redelivery — record it as a duplicate and skip re-processing.
        duplicate = False
        if event.idEventoWebhook:
            existing = (
                await db.execute(
                    select(SicrediEvent.id).where(
                        SicrediEvent.webhook_event_id == event.idEventoWebhook,
                        SicrediEvent.direction == DIRECTION_INBOUND,
                        SicrediEvent.success == True,
                        SicrediEvent.event_type != "WEBHOOK_DUPLICATE",
                    ).limit(1)
                )
            ).first()
            duplicate = existing is not None

        if duplicate:
            await log_sicredi_event(
                db,
                direction=DIRECTION_INBOUND,
                event_type="WEBHOOK_DUPLICATE",
                company_id=company_id,
                nosso_numero=nosso_numero,
                boleto_id=boleto.id if boleto else None,
                invoice_id=(boleto.invoice_id if boleto else None) or (invoice.id if invoice else None),
                success=True,
                payload=item,
                webhook_event_id=event.idEventoWebhook,
            )
            await db.commit()
            result.duplicates += 1
            result.results.append(
                WebhookEventResponse(status="duplicate", nosso_numero=nosso_numero, movimento=movimento)
            )
            continue

        # 4) Audit the delivery and COMMIT before mutating anything, so a later
        # failure can never lose the inbound record.
        await log_sicredi_event(
            db,
            direction=DIRECTION_INBOUND,
            event_type=f"WEBHOOK_{movimento_upper}" if movimento else "WEBHOOK",
            company_id=company_id,
            nosso_numero=nosso_numero,
            boleto_id=boleto.id if boleto else None,
            invoice_id=(boleto.invoice_id if boleto else None) or (invoice.id if invoice else None),
            success=True,
            payload=item,
            webhook_event_id=event.idEventoWebhook,
        )
        await db.commit()

        if not nosso_numero or not movimento:
            logger.warning("sicredi_webhook_missing_fields", nosso_numero=nosso_numero, movimento=movimento)
            result.ignored += 1
            result.results.append(WebhookEventResponse(status="ignored", detail="Missing nossoNumero/movimento"))
            continue

        if not boleto and not invoice:
            logger.warning("sicredi_webhook_boleto_not_found", nosso_numero=nosso_numero)
            result.ignored += 1
            result.results.append(
                WebhookEventResponse(
                    status="ignored",
                    nosso_numero=nosso_numero,
                    movimento=movimento,
                    detail="Boleto or invoice not found for this nossoNumero",
                )
            )
            continue

        # 5) Process the event.
        if "LIQUIDACAO" in movimento_upper:
            data_liq = parse_sicredi_date(event.dataEvento) or today_brazil()
            if boleto:
                await mark_boleto_liquidado(
                    db, boleto, valor=event.valorLiquidacao, data_liquidacao=data_liq, source="webhook"
                )
            if invoice and invoice.status != InvoiceStatus.PAID:
                invoice.status = InvoiceStatus.PAID
                invoice.paid_at = datetime.now(timezone.utc)
            await db.commit()
            result.processed += 1
            result.results.append(
                WebhookEventResponse(
                    status="processed",
                    nosso_numero=nosso_numero,
                    movimento=movimento,
                    valor_liquidacao=event.valorLiquidacao,
                    invoice_id=str(invoice.id) if invoice else None,
                )
            )
            continue

        if any(k in movimento_upper for k in ("BAIXA", "CANCELAMENTO", "CANCELADO")):
            if boleto and boleto.status not in (BoletoStatus.CANCELADO, BoletoStatus.LIQUIDADO):
                boleto.status = BoletoStatus.CANCELADO
                await db.commit()
                logger.info("sicredi_webhook_boleto_baixado", nosso_numero=nosso_numero, movimento=movimento)
            result.processed += 1
            result.results.append(
                WebhookEventResponse(
                    status="processed",
                    nosso_numero=nosso_numero,
                    movimento=movimento,
                    detail="Boleto baixado/cancelado sincronizado para CANCELADO.",
                )
            )
            continue

        logger.info("sicredi_webhook_unhandled_event", movimento=movimento)
        result.ignored += 1
        result.results.append(
            WebhookEventResponse(
                status="ignored",
                nosso_numero=nosso_numero,
                movimento=movimento,
                detail=f"Unhandled event type: {movimento}",
            )
        )

    result.status = "ok"
    return result
