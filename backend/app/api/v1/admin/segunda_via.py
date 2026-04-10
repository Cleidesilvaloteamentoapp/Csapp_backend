
"""Admin endpoints for segunda via (second copy) boleto issuance."""

from typing import Optional
from uuid import UUID
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_company_admin, require_permission
from app.models.user import Profile
from app.services import segunda_via_service

router = APIRouter(prefix="/segunda-via", tags=["Admin Segunda Via"])


class SegundaViaRequest(BaseModel):
    invoice_id: UUID
    new_due_date: Optional[date] = Field(None, description="Custom due date for the new boleto")


@router.get("/preview/{invoice_id}")
async def preview_segunda_via(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_financial")),
):
    """Preview corrected amount for an overdue invoice (penalty + interest)."""
    try:
        result = await segunda_via_service.preview_segunda_via(
            db, admin.company_id, invoice_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "invoice_id": result["invoice_id"],
        "installment_number": result["installment_number"],
        "original_amount": float(result["original_amount"]),
        "penalty": float(result["penalty"]),
        "interest": float(result["interest"]),
        "corrected_amount": float(result["corrected_amount"]),
        "days_overdue": result["days_overdue"],
        "new_due_date": result["new_due_date"].isoformat(),
    }


@router.post("/issue", status_code=status.HTTP_201_CREATED)
async def issue_segunda_via(
    data: SegundaViaRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_financial")),
):
    """Issue a second copy boleto with automatic penalty/interest calculation.

    Returns corrected values. Use the Sicredi endpoints to create the actual
    boleto with the corrected amount and new due date.
    """
    try:
        result = await segunda_via_service.issue_segunda_via(
            db, admin.company_id, data.invoice_id,
            performed_by=admin.id,
            ip_address=request.client.host if request.client else None,
            new_due_date=data.new_due_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "invoice_id": result["invoice_id"],
        "client_id": result["client_id"],
        "client_lot_id": result["client_lot_id"],
        "installment_number": result["installment_number"],
        "original_amount": float(result["original_amount"]),
        "penalty": float(result["penalty"]),
        "interest": float(result["interest"]),
        "corrected_amount": float(result["corrected_amount"]),
        "days_overdue": result["days_overdue"],
        "new_due_date": result["new_due_date"].isoformat(),
    }
