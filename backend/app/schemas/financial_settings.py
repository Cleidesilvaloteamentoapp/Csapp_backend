
"""Schemas for company financial settings and per-client-lot financial rules."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Company Financial Settings (global defaults per company)
# ---------------------------------------------------------------------------

class CompanyFinancialSettingsResponse(BaseModel):
    """Response schema for company financial settings."""

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


class CompanyFinancialSettingsUpdate(BaseModel):
    """Update schema for company financial settings. All fields optional."""

    penalty_rate: Optional[Decimal] = Field(None, ge=0, le=1, description="Penalty rate, e.g. 0.02 = 2%")
    daily_interest_rate: Optional[Decimal] = Field(None, ge=0, le=0.01, description="Daily interest rate, e.g. 0.00033 = 0.033%/day")
    adjustment_index: Optional[str] = Field(None, pattern=r"^(IPCA|IGPM|CUB|INPC)$", description="Price index: IPCA, IGPM, CUB, INPC")
    adjustment_frequency: Optional[str] = Field(None, pattern=r"^(MONTHLY|QUARTERLY|SEMIANNUAL|ANNUAL)$", description="Adjustment frequency")
    adjustment_custom_rate: Optional[Decimal] = Field(None, ge=0, le=1, description="Fixed annual rate on top of index, e.g. 0.05 = 5%")


# ---------------------------------------------------------------------------
# ClientLot Financial Rules (per-client override)
# ---------------------------------------------------------------------------

class ClientLotFinancialUpdate(BaseModel):
    """Update financial rules on a specific client-lot. All fields optional.
    Set a field to null to clear the override (will fall back to company defaults).
    """

    penalty_rate: Optional[Decimal] = Field(None, ge=0, le=1, description="Custom penalty rate, e.g. 0.02 = 2%. Null = use company default.")
    daily_interest_rate: Optional[Decimal] = Field(None, ge=0, le=0.01, description="Custom daily interest rate. Null = use company default.")
    adjustment_index: Optional[str] = Field(None, pattern=r"^(IPCA|IGPM|CUB|INPC)$", description="Custom price index. Null = use company default.")
    adjustment_frequency: Optional[str] = Field(None, pattern=r"^(MONTHLY|QUARTERLY|SEMIANNUAL|ANNUAL)$", description="Custom frequency. Null = use company default.")
    adjustment_custom_rate: Optional[Decimal] = Field(None, ge=0, le=1, description="Custom fixed rate. Null = use company default.")
    annual_adjustment_rate: Optional[Decimal] = Field(None, ge=0, le=1, description="Legacy fixed annual rate on top of IPCA.")
