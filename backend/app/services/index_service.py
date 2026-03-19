
"""Service for fetching and managing economic indices (IPCA, IGPM, INPC, CUB).

Extends the original ipca_service with multi-index support and manual overrides.
Manual values from economic_indices table take precedence over API-fetched values.
"""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from uuid import UUID

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.economic_index import EconomicIndex
from app.models.enums import AdjustmentIndex, IndexSource
from app.utils.logging import get_logger

logger = get_logger(__name__)

# BCB SGS API series codes
BCB_SERIES = {
    AdjustmentIndex.IPCA: 433,
    AdjustmentIndex.IGPM: 189,
    AdjustmentIndex.INPC: 188,
    # CUB has no BCB series — always manual
}

BCB_SGS_BASE = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series}/dados"


async def _fetch_bcb_series(
    series: int,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """Fetch monthly values from BCB SGS API."""
    url = BCB_SGS_BASE.format(series=series)
    fmt = "%d/%m/%Y"
    params = {
        "formato": "json",
        "dataInicial": start_date.strftime(fmt),
        "dataFinal": end_date.strftime(fmt),
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    logger.error("bcb_api_error", series=series, status=resp.status)
                    return []
                data = await resp.json()
                return data if isinstance(data, list) else []
    except Exception as exc:
        logger.error("bcb_api_exception", series=series, error=str(exc))
        return []


async def get_manual_index_value(
    db: AsyncSession,
    company_id: UUID,
    index_type: AdjustmentIndex,
    reference_month: date,
    state_code: Optional[str] = None,
) -> Optional[Decimal]:
    """Look up a manually entered index value from the economic_indices table."""
    stmt = select(EconomicIndex.value).where(
        EconomicIndex.company_id == company_id,
        EconomicIndex.index_type == index_type,
        EconomicIndex.reference_month == date(reference_month.year, reference_month.month, 1),
    )
    if state_code and index_type == AdjustmentIndex.CUB:
        stmt = stmt.where(EconomicIndex.state_code == state_code.upper())
    result = await db.execute(stmt)
    val = result.scalar_one_or_none()
    return Decimal(str(val)) if val is not None else None


async def get_accumulated_index(
    index_type: AdjustmentIndex,
    reference_date: Optional[date] = None,
    db: Optional[AsyncSession] = None,
    company_id: Optional[UUID] = None,
    state_code: Optional[str] = None,
    months: int = 12,
) -> Decimal:
    """Calculate accumulated index for the last N months.

    Priority: manual DB values > BCB API values.
    CUB is always manual (no BCB API).

    Returns accumulated percentage (e.g. 4.52 for 4.52%).
    """
    ref = reference_date or date.today()
    start = date(ref.year - 1, ref.month, 1) if months >= 12 else date(ref.year, ref.month - months, 1)
    end = date(ref.year, ref.month, 1)

    monthly_values: list[Decimal] = []

    # Try manual values first if DB session available
    if db and company_id:
        current = start
        while current <= end:
            val = await get_manual_index_value(db, company_id, index_type, current, state_code)
            if val is not None:
                monthly_values.append(val)
            current = date(
                current.year + (1 if current.month == 12 else 0),
                (current.month % 12) + 1,
                1,
            )

    # If we got enough manual values, use them
    if len(monthly_values) >= months:
        entries = monthly_values[-months:]
    elif index_type == AdjustmentIndex.CUB:
        # CUB is always manual — if not enough data, return 0
        logger.warning("cub_insufficient_data", count=len(monthly_values), required=months)
        entries = monthly_values if monthly_values else []
        if not entries:
            return Decimal("0")
    else:
        # Fetch from BCB API for IPCA/IGPM/INPC
        series = BCB_SERIES.get(index_type)
        if not series:
            return Decimal("0")

        api_data = await _fetch_bcb_series(series, start, end)
        if not api_data:
            logger.warning("index_no_api_data", index=index_type.value)
            return Decimal("0")

        entries = []
        for entry in api_data[-months:]:
            try:
                val = Decimal(entry["valor"].replace(",", "."))
                entries.append(val)
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning("index_parse_error", entry=entry, error=str(exc))
                continue

    # Calculate accumulated: ((1 + m1/100) * (1 + m2/100) * ... - 1) * 100
    accumulated = Decimal("1")
    for rate in entries:
        accumulated *= (Decimal("1") + rate / Decimal("100"))

    result = ((accumulated - Decimal("1")) * Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    logger.info("index_accumulated", index=index_type.value, pct=str(result), months=len(entries))
    return result


def calculate_adjusted_value(
    current_value: Decimal,
    index_pct: Decimal,
    fixed_rate_pct: Decimal = Decimal("5"),
) -> dict:
    """Apply adjustment: value + fixed_rate% + index%.

    Args:
        current_value: Current installment value
        index_pct: Accumulated index percentage (e.g. 4.52)
        fixed_rate_pct: Fixed annual rate percentage (default 5%)

    Returns dict with original_value, index_adjustment, fixed_adjustment, new_value
    """
    index_adj = (current_value * index_pct / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    fixed_adj = (current_value * fixed_rate_pct / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    new_value = current_value + index_adj + fixed_adj

    return {
        "original_value": current_value,
        "index_pct": index_pct,
        "index_adjustment": index_adj,
        "fixed_rate_pct": fixed_rate_pct,
        "fixed_adjustment": fixed_adj,
        "new_value": new_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
    }
