
"""Shared boleto status transitions used by the webhook, the sync tasks, and
the manual sync endpoint.

Centralizing the "mark as paid" logic guarantees the three code paths stay
aligned: they all set data_liquidacao from the bank-reported date (in the
America/Sao_Paulo timezone, not UTC) and update the linked invoice the same
way, and they are all idempotent so a duplicate webhook/redelivery cannot
overwrite a liquidation already recorded.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.boleto import Boleto
from app.models.enums import BoletoStatus, InvoiceStatus
from app.models.invoice import Invoice
from app.utils.logging import get_logger

logger = get_logger(__name__)

_BRAZIL_TZ = ZoneInfo("America/Sao_Paulo")

# Accepted Sicredi date formats (dataEvento / dataLiquidacao come in a few shapes).
_DATE_FORMATS = (
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
)


def today_brazil() -> date:
    """Current date in America/Sao_Paulo, so evening payments are not logged a day late."""
    return datetime.now(_BRAZIL_TZ).date()


def parse_sicredi_date(value: Optional[str]) -> Optional[date]:
    """Parse a Sicredi-provided date string into a date, or None if unparseable."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    # Last resort: ISO 8601 with timezone offset (e.g. 2026-07-14T21:30:00-03:00).
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        logger.warning("sicredi_date_unparseable", value=text[:40])
        return None


async def mark_boleto_liquidado(
    db: AsyncSession,
    boleto: Boleto,
    *,
    valor: Optional[Decimal] = None,
    data_liquidacao: Optional[date] = None,
    source: str,
) -> bool:
    """Mark a boleto (and its linked invoice) as paid. Idempotent.

    Returns True if the boleto transitioned to LIQUIDADO on this call, False if
    it was already LIQUIDADO (existing data_liquidacao/valor_liquidacao are
    preserved and not clobbered by a redelivered event).

    The caller is responsible for flushing/committing the transaction.
    """
    if boleto.status == BoletoStatus.LIQUIDADO:
        return False

    boleto.status = BoletoStatus.LIQUIDADO
    boleto.data_liquidacao = data_liquidacao or today_brazil()
    if valor is not None:
        boleto.valor_liquidacao = valor

    logger.info(
        "boleto_marked_liquidado",
        boleto_id=str(boleto.id),
        nosso_numero=boleto.nosso_numero,
        source=source,
        data_liquidacao=str(boleto.data_liquidacao),
    )

    if boleto.invoice_id:
        inv = (
            await db.execute(select(Invoice).where(Invoice.id == boleto.invoice_id))
        ).scalar_one_or_none()
        if inv and inv.status != InvoiceStatus.PAID:
            inv.status = InvoiceStatus.PAID
            inv.paid_at = datetime.now(timezone.utc)

    await db.flush()
    return True
