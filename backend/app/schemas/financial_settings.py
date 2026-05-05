
"""Schemas for company financial settings and per-client-lot financial rules."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Rate conversion helpers (percentage <-> decimal)
# ---------------------------------------------------------------------------

def rate_from_percent(v, max_percent: int = 100):
    """Convert a percentage input (e.g. 2 for 2%) to decimal (0.02) for DB storage."""
    if v is None:
        return v
    d = Decimal(str(v))
    if d < 0 or d > max_percent:
        raise ValueError(f"Value must be between 0 and {max_percent}")
    return d / Decimal("100")


def rate_to_percent(v):
    """Convert a decimal from DB (e.g. 0.02) to percentage (2) for API response."""
    if v is None:
        return v
    return Decimal(str(v)) * Decimal("100")


# ---------------------------------------------------------------------------
# Company Financial Settings (global defaults per company)
# ---------------------------------------------------------------------------

class CompanyFinancialSettingsResponse(BaseModel):
    """Response schema for company financial settings.

    All rate fields are returned as percentages (e.g. 2 = 2%).
    """

    id: UUID
    company_id: UUID
    penalty_rate: Decimal
    daily_interest_rate: Decimal
    adjustment_index: str
    adjustment_frequency: str
    adjustment_custom_rate: Decimal
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("penalty_rate", "daily_interest_rate", "adjustment_custom_rate", mode="before")
    @classmethod
    def db_to_percent(cls, v):
        return rate_to_percent(v)


class CompanyFinancialSettingsUpdate(BaseModel):
    """Update schema for company financial settings. All fields optional.

    All rate fields accept percentages: send 2 for 2%, 0.5 for 0.5%.
    """

    penalty_rate: Optional[Decimal] = Field(None, description="Penalty rate in %, e.g. 2 = 2%")
    daily_interest_rate: Optional[Decimal] = Field(None, description="Daily interest rate in %, e.g. 0.033 = 0.033%/day")
    adjustment_index: Optional[str] = Field(None, pattern=r"^(IPCA|IGPM|CUB|INPC)$", description="Price index: IPCA, IGPM, CUB, INPC")
    adjustment_frequency: Optional[str] = Field(None, pattern=r"^(MONTHLY|QUARTERLY|SEMIANNUAL|ANNUAL)$", description="Adjustment frequency")
    adjustment_custom_rate: Optional[Decimal] = Field(None, description="Fixed annual rate in %, e.g. 5 = 5%")

    @field_validator("penalty_rate", "adjustment_custom_rate", mode="before")
    @classmethod
    def percent_to_decimal(cls, v):
        return rate_from_percent(v, max_percent=100)

    @field_validator("daily_interest_rate", mode="before")
    @classmethod
    def daily_percent_to_decimal(cls, v):
        return rate_from_percent(v, max_percent=1)


# ---------------------------------------------------------------------------
# ClientLot Financial Rules (per-client override)
# ---------------------------------------------------------------------------

class ClientLotFinancialUpdate(BaseModel):
    """Update financial rules on a specific client-lot. All fields optional.
    Set a field to null to clear the override (will fall back to company defaults).

    All rate fields accept percentages: send 2 for 2%, 0.5 for 0.5%.
    """

    penalty_rate: Optional[Decimal] = Field(None, description="Custom penalty rate in %, e.g. 2 = 2%. Null = use company default.")
    daily_interest_rate: Optional[Decimal] = Field(None, description="Custom daily interest rate in %, e.g. 0.033 = 0.033%/day. Null = use company default.")
    adjustment_index: Optional[str] = Field(None, pattern=r"^(IPCA|IGPM|CUB|INPC)$", description="Custom price index. Null = use company default.")
    adjustment_frequency: Optional[str] = Field(None, pattern=r"^(MONTHLY|QUARTERLY|SEMIANNUAL|ANNUAL)$", description="Custom frequency. Null = use company default.")
    adjustment_custom_rate: Optional[Decimal] = Field(None, description="Custom fixed rate in %, e.g. 5 = 5%. Null = use company default.")
    annual_adjustment_rate: Optional[Decimal] = Field(None, description="Legacy fixed annual rate in %, e.g. 5 = 5%.")

    @field_validator("penalty_rate", "adjustment_custom_rate", "annual_adjustment_rate", mode="before")
    @classmethod
    def percent_to_decimal(cls, v):
        return rate_from_percent(v, max_percent=100)

    @field_validator("daily_interest_rate", mode="before")
    @classmethod
    def daily_percent_to_decimal(cls, v):
        return rate_from_percent(v, max_percent=1)
