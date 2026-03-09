
"""Service for fetching IPCA index from Brazilian Central Bank (BCB) API."""

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

import aiohttp

from app.utils.logging import get_logger

logger = get_logger(__name__)

# BCB SGS API - Series 433 = IPCA mensal
BCB_SGS_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados"


async def fetch_ipca_monthly(
    start_date: date,
    end_date: date,
) -> list[dict]:
    """Fetch monthly IPCA values from BCB SGS API.

    Returns list of {"data": "dd/mm/yyyy", "valor": "0.XX"} entries.
    """
    fmt = "%d/%m/%Y"
    params = {
        "formato": "json",
        "dataInicial": start_date.strftime(fmt),
        "dataFinal": end_date.strftime(fmt),
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(BCB_SGS_URL, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    logger.error("bcb_api_error", status=resp.status, body=await resp.text())
                    return []
                data = await resp.json()
                return data if isinstance(data, list) else []
    except Exception as exc:
        logger.error("bcb_api_exception", error=str(exc))
        return []


async def get_ipca_accumulated_12_months(
    reference_date: Optional[date] = None,
) -> Decimal:
    """Calculate accumulated IPCA for the last 12 months.

    Formula: ((1 + m1/100) * (1 + m2/100) * ... * (1 + m12/100) - 1) * 100
    Returns the accumulated percentage (e.g. 4.52 for 4.52%).
    """
    ref = reference_date or date.today()
    # Go back 13 months to ensure we get 12 full months
    start = date(ref.year - 1, ref.month, 1)
    end = date(ref.year, ref.month, 1)

    monthly_data = await fetch_ipca_monthly(start, end)

    if not monthly_data:
        logger.warning("ipca_no_data", start=start.isoformat(), end=end.isoformat())
        return Decimal("0")

    # Take the last 12 entries
    entries = monthly_data[-12:]

    accumulated = Decimal("1")
    for entry in entries:
        try:
            rate = Decimal(entry["valor"].replace(",", ".")) / Decimal("100")
            accumulated *= (Decimal("1") + rate)
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("ipca_parse_error", entry=entry, error=str(exc))
            continue

    # Convert back to percentage
    ipca_pct = ((accumulated - Decimal("1")) * Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    logger.info("ipca_accumulated", pct=str(ipca_pct), months=len(entries))
    return ipca_pct


def calculate_adjusted_value(
    current_value: Decimal,
    ipca_pct: Decimal,
    fixed_rate_pct: Decimal = Decimal("5"),
) -> dict:
    """Apply annual adjustment: value + fixed_rate% + IPCA%.

    Args:
        current_value: Current installment value
        ipca_pct: Accumulated IPCA percentage (e.g. 4.52)
        fixed_rate_pct: Fixed annual rate percentage (default 5%)

    Returns dict with original_value, ipca_adjustment, fixed_adjustment, new_value
    """
    ipca_adj = (current_value * ipca_pct / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    fixed_adj = (current_value * fixed_rate_pct / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    new_value = current_value + ipca_adj + fixed_adj

    return {
        "original_value": current_value,
        "ipca_pct": ipca_pct,
        "ipca_adjustment": ipca_adj,
        "fixed_rate_pct": fixed_rate_pct,
        "fixed_adjustment": fixed_adj,
        "new_value": new_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
    }
