
"""Admin endpoints for managing company-wide financial defaults."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.database import get_db
from app.core.deps import get_company_admin
from app.models.company_financial_settings import CompanyFinancialSettings
from app.models.enums import AdjustmentFrequency, AdjustmentIndex
from app.models.user import Profile
from app.schemas.financial_settings import (
    CompanyFinancialSettingsResponse,
    CompanyFinancialSettingsUpdate,
)

router = APIRouter(prefix="/financial-settings", tags=["Admin Financial Settings"])


async def _get_or_create_settings(
    db: AsyncSession, company_id,
) -> CompanyFinancialSettings:
    """Return existing settings or auto-create a row with defaults."""
    row = await db.execute(
        select(CompanyFinancialSettings).where(
            CompanyFinancialSettings.company_id == company_id
        )
    )
    settings = row.scalar_one_or_none()
    if settings is None:
        settings = CompanyFinancialSettings(company_id=company_id)
        db.add(settings)
        await db.flush()
    return settings


@router.get("/", response_model=CompanyFinancialSettingsResponse)
async def get_financial_settings(
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Get the company's global financial defaults.

    Auto-creates a row with system defaults if none exists yet.
    """
    settings = await _get_or_create_settings(db, admin.company_id)
    return CompanyFinancialSettingsResponse.model_validate(settings)


@router.put("/", response_model=CompanyFinancialSettingsResponse)
async def update_financial_settings(
    data: CompanyFinancialSettingsUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Update the company's global financial defaults.

    Only provided fields are updated; omitted fields remain unchanged.
    """
    settings = await _get_or_create_settings(db, admin.company_id)

    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        if field == "adjustment_index" and value is not None:
            value = AdjustmentIndex(value)
        elif field == "adjustment_frequency" and value is not None:
            value = AdjustmentFrequency(value)
        setattr(settings, field, value)

    await db.flush()

    await log_audit(
        db,
        user_id=admin.id,
        company_id=admin.company_id,
        table_name="company_financial_settings",
        operation="UPDATE",
        resource_id=str(settings.id),
        detail=f"Financial settings updated: {list(updates.keys())}",
        ip_address=request.client.host if request.client else None,
    )

    return CompanyFinancialSettingsResponse.model_validate(settings)
