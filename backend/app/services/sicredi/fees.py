"""Translation between the app's fee vocabulary and Sicredi's wire vocabulary.

Sicredi's ``POST /boletos`` accepts exactly two values in ``tipoJuros``,
``tipoMulta`` and ``tipoDesconto``: ``VALOR`` and ``PERCENTUAL``. For juros they
mean R$/day and %/month respectively; for multa and desconto, R$ and % over the
boleto value.

The app (API and UI) speaks a more explicit vocabulary — ``VALOR_DIA``,
``PERCENTUAL_MES``, ``PERCENTUAL_DIA``, ``ISENTO`` — because a contract states
its late-payment rules that way ("juros de 0,33% ao dia"). Anything that reaches
Sicredi untranslated is rejected with HTTP 400 *before* the boleto is
registered, so every outbound payload must pass through here.

``ISENTO`` (or a missing/zero amount) means the field is omitted entirely: the
type and its paired amount are both dropped, since Sicredi rejects an amount
without its type.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

# Sicredi wire vocabulary — the only two values the API understands.
SICREDI_VALOR = "VALOR"
SICREDI_PERCENTUAL = "PERCENTUAL"

# Sicredi registers juros per month, while contracts state them per day.
# Same convention already used to render fee text from the stored daily rates
# (see app.tasks.batch_tasks._format_fee_lines_from_rates).
DAYS_PER_MONTH = Decimal("30")

ISENTO = "ISENTO"

#: Juros: app vocabulary -> (Sicredi type, multiplier applied to the amount).
_JUROS_MAP: dict[str, tuple[str, Decimal]] = {
    "VALOR_DIA": (SICREDI_VALOR, Decimal("1")),
    "PERCENTUAL_MES": (SICREDI_PERCENTUAL, Decimal("1")),
    "PERCENTUAL_DIA": (SICREDI_PERCENTUAL, DAYS_PER_MONTH),
    # Already in wire vocabulary: older batch_operations.input_data rows and
    # direct API callers may carry these.
    SICREDI_VALOR: (SICREDI_VALOR, Decimal("1")),
    SICREDI_PERCENTUAL: (SICREDI_PERCENTUAL, Decimal("1")),
}

#: Multa and desconto have no per-day/per-month ambiguity.
_FLAT_MAP: dict[str, tuple[str, Decimal]] = {
    SICREDI_VALOR: (SICREDI_VALOR, Decimal("1")),
    SICREDI_PERCENTUAL: (SICREDI_PERCENTUAL, Decimal("1")),
}

#: Accepted app-side values, for API-boundary validation and error messages.
JUROS_TYPES = (ISENTO, "VALOR_DIA", "PERCENTUAL_MES", "PERCENTUAL_DIA")
MULTA_TYPES = (ISENTO, SICREDI_VALOR, SICREDI_PERCENTUAL)
DESCONTO_TYPES = MULTA_TYPES

#: Regex for Pydantic ``pattern=`` on the inbound API schemas.
JUROS_PATTERN = r"^(ISENTO|VALOR_DIA|PERCENTUAL_MES|PERCENTUAL_DIA|VALOR|PERCENTUAL)$"
MULTA_PATTERN = r"^(ISENTO|VALOR|PERCENTUAL)$"
DESCONTO_PATTERN = MULTA_PATTERN


def _normalize(
    tipo: Optional[str],
    valor: Optional[Decimal],
    mapping: dict[str, tuple[str, Decimal]],
    field: str,
) -> tuple[Optional[str], Optional[Decimal]]:
    """Translate one (tipo, valor) pair into Sicredi's vocabulary.

    Returns ``(None, None)`` when the fee does not apply, so the caller can omit
    both fields from the payload.
    """
    if tipo is None or not str(tipo).strip():
        return None, None

    key = str(tipo).strip().upper()
    if key == ISENTO:
        return None, None

    if key not in mapping:
        raise ValueError(
            f"{field}: '{tipo}' is not a value Sicredi understands. "
            f"Expected one of {', '.join(sorted(mapping))} or {ISENTO}."
        )

    # A type without an amount (or with zero) is the same as exempt; sending the
    # type alone is rejected by Sicredi.
    if valor is None or Decimal(str(valor)) <= 0:
        return None, None

    sicredi_tipo, multiplier = mapping[key]
    amount = (Decimal(str(valor)) * multiplier).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return sicredi_tipo, amount


def normalize_juros(
    tipo: Optional[str], valor: Optional[Decimal]
) -> tuple[Optional[str], Optional[Decimal]]:
    """``("PERCENTUAL_DIA", 0.33)`` -> ``("PERCENTUAL", 9.90)``."""
    return _normalize(tipo, valor, _JUROS_MAP, "tipoJuros")


def normalize_multa(
    tipo: Optional[str], valor: Optional[Decimal]
) -> tuple[Optional[str], Optional[Decimal]]:
    """``("PERCENTUAL", 5)`` -> ``("PERCENTUAL", 5.00)``."""
    return _normalize(tipo, valor, _FLAT_MAP, "tipoMulta")


def normalize_desconto(
    tipo: Optional[str], valor: Optional[Decimal]
) -> tuple[Optional[str], Optional[Decimal]]:
    """Same vocabulary as multa; the amount is the first discount tier."""
    return _normalize(tipo, valor, _FLAT_MAP, "tipoDesconto")
