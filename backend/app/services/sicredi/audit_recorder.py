
"""Per-request/per-task recorder for outbound Sicredi API calls.

``SicrediClient`` is cached and shared across concurrent requests, so it cannot
hold a mutable audit buffer of its own. Instead the client pushes a
``RecordedCall`` into a ``ContextVar`` sink on every request; the caller (an HTTP
dependency or a Celery task) opens a recording scope around the work and, when it
finishes, drains the sink and persists one ``sicredi_events`` row per call.

When no scope is active ``record_call`` is a no-op, so background jobs that keep
their own summary audit (the sync tasks) don't get flooded with per-call rows.
"""

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

_sink: ContextVar[Optional[list]] = ContextVar("sicredi_audit_sink", default=None)


@dataclass
class RecordedCall:
    company_id: Optional[UUID]
    method: str
    url: str
    status_code: Optional[int]
    success: bool
    request_payload: Any
    response_payload: Any
    nosso_numero: Optional[str]


def start_recording() -> Token:
    """Begin a recording scope; returns a token to pass to ``stop_recording``."""
    return _sink.set([])


def stop_recording(token: Token) -> list:
    """End the scope and return everything recorded within it."""
    calls = _sink.get() or []
    _sink.reset(token)
    return calls


def record_call(
    *,
    company_id: Optional[UUID],
    method: str,
    url: str,
    status_code: Optional[int],
    success: bool,
    request_payload: Any = None,
    response_payload: Any = None,
    nosso_numero: Optional[str] = None,
) -> None:
    """Record one Sicredi call, if a recording scope is active (else no-op)."""
    sink = _sink.get()
    if sink is None:
        return
    sink.append(
        RecordedCall(
            company_id=company_id,
            method=method,
            url=url,
            status_code=status_code,
            success=success,
            request_payload=request_payload,
            response_payload=response_payload,
            nosso_numero=nosso_numero or nosso_numero_for(url, None, request_payload),
        )
    )


# URL suffix -> audit event_type. Checked in order; first match wins.
_EVENT_TYPE_RULES = (
    ("/data-vencimento", "ALTERAR_VENCIMENTO"),
    ("/seu-numero", "ALTERAR_SEU_NUMERO"),
    ("/desconto", "ALTERAR_DESCONTO"),
    ("/juros", "ALTERAR_JUROS"),
    ("/conceder-abatimento", "CONCEDER_ABATIMENTO"),
    ("/cancelar-abatimento", "CANCELAR_ABATIMENTO"),
    ("/sustar-negativacao-baixar-titulo", "SUSTAR_NEGATIVACAO_BAIXAR"),
    ("/negativacao", "NEGATIVACAO"),
    ("/baixa", "BAIXA_BOLETO"),
    ("/boletos/pdf", "PDF_BOLETO"),
    ("/boletos/liquidados", "CONSULTA_LIQUIDADOS"),
    ("/boletos/cadastrados", "CONSULTA_SEU_NUMERO"),
    ("/webhook/contrato", "WEBHOOK_CONTRATO"),
)


def event_type_for(method: str, url: str) -> str:
    """Classify a Sicredi call into an audit event_type from its method + URL."""
    path = url.split("?", 1)[0]
    for suffix, name in _EVENT_TYPE_RULES:
        if path.endswith(suffix) or suffix in path:
            return name
    # Bare /boletos: POST creates, GET queries.
    if path.endswith("/boletos"):
        return "CREATE_BOLETO" if method.upper() == "POST" else "CONSULTA_BOLETO"
    if "/boletos/" in path:
        return "CONSULTA_BOLETO" if method.upper() == "GET" else "API_CALL"
    return "API_CALL"


async def persist_recorded_calls(db, calls: list) -> None:
    """Write recorded outbound calls to the audit trail on the given session.

    Successful PDF downloads are skipped to limit noise; their failures are kept.
    Best-effort per call — never raises. The caller commits.
    """
    from app.services.sicredi_audit_service import DIRECTION_OUTBOUND, log_sicredi_event

    for call in calls:
        event_type = event_type_for(call.method, call.url)
        if event_type == "PDF_BOLETO" and call.success:
            continue
        await log_sicredi_event(
            db,
            direction=DIRECTION_OUTBOUND,
            event_type=event_type,
            company_id=call.company_id,
            nosso_numero=call.nosso_numero,
            http_status=call.status_code,
            success=call.success,
            payload={
                "method": call.method,
                "url": call.url,
                "request": call.request_payload,
                "response": call.response_payload,
            },
        )


def nosso_numero_for(url: str, params: Optional[dict], body: Any = None) -> Optional[str]:
    """Best-effort extraction of the nossoNumero a call refers to."""
    if params and params.get("nossoNumero"):
        return str(params["nossoNumero"])
    if isinstance(body, dict) and body.get("nossoNumero"):
        return str(body["nossoNumero"])
    path = url.split("?", 1)[0]
    if "/boletos/" in path:
        tail = path.split("/boletos/", 1)[1]
        segment = tail.split("/", 1)[0]
        if segment and segment not in ("pdf", "cadastrados", "liquidados"):
            return segment
    return None
