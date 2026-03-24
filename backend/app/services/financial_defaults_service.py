
"""Service for resolving effective financial rates with 3-tier fallback.

Priority: per-lot override → company_financial_settings → hardcoded constants.
"""

from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client_lot import ClientLot
from app.models.company_financial_settings import CompanyFinancialSettings
from app.models.enums import AdjustmentFrequency, AdjustmentIndex

# Hardcoded system defaults (last-resort fallback)
HARDCODED_PENALTY_RATE = Decimal("0.02")
HARDCODED_DAILY_INTEREST_RATE = Decimal("0.000330")
HARDCODED_ADJUSTMENT_INDEX = AdjustmentIndex.IPCA
HARDCODED_ADJUSTMENT_FREQUENCY = AdjustmentFrequency.ANNUAL
HARDCODED_ADJUSTMENT_CUSTOM_RATE = Decimal("0.05")


async def get_company_settings(
    db: AsyncSession, company_id: UUID
) -> Optional[CompanyFinancialSettings]:
    """Load company financial settings (cached per request via SQLAlchemy identity map)."""
    row = await db.execute(
        select(CompanyFinancialSettings).where(
            CompanyFinancialSettings.company_id == company_id
        )
    )
    return row.scalar_one_or_none()


async def get_effective_penalty_rate(
    db: AsyncSession, client_lot: ClientLot
) -> Decimal:
    """Resolve penalty rate: per-lot → company → hardcoded."""
    if client_lot.penalty_rate is not None:
        return client_lot.penalty_rate
    cfs = await get_company_settings(db, client_lot.company_id)
    if cfs and cfs.penalty_rate is not None:
        return cfs.penalty_rate
    return HARDCODED_PENALTY_RATE


async def get_effective_daily_interest_rate(
    db: AsyncSession, client_lot: ClientLot
) -> Decimal:
    """Resolve daily interest rate: per-lot → company → hardcoded."""
    if client_lot.daily_interest_rate is not None:
        return client_lot.daily_interest_rate
    cfs = await get_company_settings(db, client_lot.company_id)
    if cfs and cfs.daily_interest_rate is not None:
        return cfs.daily_interest_rate
    return HARDCODED_DAILY_INTEREST_RATE


async def get_effective_adjustment_index(
    db: AsyncSession, client_lot: ClientLot
) -> AdjustmentIndex:
    """Resolve adjustment index: per-lot → company → hardcoded (IPCA)."""
    if client_lot.adjustment_index is not None:
        return client_lot.adjustment_index
    cfs = await get_company_settings(db, client_lot.company_id)
    if cfs and cfs.adjustment_index is not None:
        return cfs.adjustment_index
    return HARDCODED_ADJUSTMENT_INDEX


async def get_effective_adjustment_frequency(
    db: AsyncSession, client_lot: ClientLot
) -> AdjustmentFrequency:
    """Resolve adjustment frequency: per-lot → company → hardcoded (ANNUAL)."""
    if client_lot.adjustment_frequency is not None:
        return client_lot.adjustment_frequency
    cfs = await get_company_settings(db, client_lot.company_id)
    if cfs and cfs.adjustment_frequency is not None:
        return cfs.adjustment_frequency
    return HARDCODED_ADJUSTMENT_FREQUENCY


async def get_effective_custom_rate(
    db: AsyncSession, client_lot: ClientLot
) -> Decimal:
    """Resolve custom fixed rate: per-lot → company → hardcoded (5%)."""
    if client_lot.adjustment_custom_rate is not None:
        return client_lot.adjustment_custom_rate
    cfs = await get_company_settings(db, client_lot.company_id)
    if cfs and cfs.adjustment_custom_rate is not None:
        return cfs.adjustment_custom_rate
    return HARDCODED_ADJUSTMENT_CUSTOM_RATE


async def get_all_effective_rates(
    db: AsyncSession, client_lot: ClientLot
) -> dict:
    """Resolve all financial rates at once (minimizes DB queries).

    Returns dict with: penalty_rate, daily_interest_rate, adjustment_index,
    adjustment_frequency, adjustment_custom_rate.
    """
    cfs = await get_company_settings(db, client_lot.company_id)

    def _resolve(lot_val, cfs_val, hardcoded):
        if lot_val is not None:
            return lot_val
        if cfs and cfs_val is not None:
            return cfs_val
        return hardcoded

    return {
        "penalty_rate": _resolve(
            client_lot.penalty_rate,
            cfs.penalty_rate if cfs else None,
            HARDCODED_PENALTY_RATE,
        ),
        "daily_interest_rate": _resolve(
            client_lot.daily_interest_rate,
            cfs.daily_interest_rate if cfs else None,
            HARDCODED_DAILY_INTEREST_RATE,
        ),
        "adjustment_index": _resolve(
            client_lot.adjustment_index,
            cfs.adjustment_index if cfs else None,
            HARDCODED_ADJUSTMENT_INDEX,
        ),
        "adjustment_frequency": _resolve(
            client_lot.adjustment_frequency,
            cfs.adjustment_frequency if cfs else None,
            HARDCODED_ADJUSTMENT_FREQUENCY,
        ),
        "adjustment_custom_rate": _resolve(
            client_lot.adjustment_custom_rate,
            cfs.adjustment_custom_rate if cfs else None,
            HARDCODED_ADJUSTMENT_CUSTOM_RATE,
        ),
    }
