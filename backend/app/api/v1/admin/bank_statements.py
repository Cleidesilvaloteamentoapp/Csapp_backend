
"""Admin endpoints for bank statement (francesinha) upload and reconciliation.

This is a stub implementation — the actual parsing logic will be implemented
per-bank via the BankProvider.parse_bank_statement interface.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.database import get_db
from app.core.deps import get_company_admin
from app.models.user import Profile
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/bank-statements", tags=["Admin Bank Statements"])


@router.post("/upload")
async def upload_bank_statement(
    file: UploadFile = File(..., description="Bank statement file (CNAB 240/400 or OFX)"),
    bank_code: str = Query("748", description="FEBRABAN bank code (default: 748 = Sicredi)"),
    file_type: str = Query("cnab240", description="File format: cnab240, cnab400, ofx"),
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Upload a bank statement file for reconciliation.

    Parses the file and returns structured transaction data that can be
    matched against existing boletos/invoices.

    **Status: STUB** — parsing logic will be implemented per-bank.
    """
    if file.content_type and file.content_type not in (
        "application/octet-stream",
        "text/plain",
        "application/xml",
        "text/xml",
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    if len(content) > 10 * 1024 * 1024:  # 10 MB limit
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")

    # Try to get the bank provider
    try:
        from app.services.bank.registry import get_bank_provider
        provider_cls = get_bank_provider(bank_code)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"No bank integration registered for code '{bank_code}'",
        )

    # Instantiate and try parsing
    try:
        provider = provider_cls(db=db, company_id=admin.company_id)
        transactions = await provider.parse_bank_statement(content, file_type)
    except NotImplementedError:
        raise HTTPException(
            status_code=501,
            detail=(
                f"Bank statement parsing is not yet implemented for "
                f"{provider.bank_name} ({bank_code}). "
                f"This feature is under development."
            ),
        )
    except Exception as exc:
        logger.error("bank_statement_parse_error", error=str(exc))
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(exc)}")

    await log_audit(
        db,
        user_id=admin.id,
        company_id=admin.company_id,
        table_name="boletos",
        operation="BANK_STATEMENT_UPLOAD",
        detail=f"Uploaded {file_type} from bank {bank_code}: {len(transactions)} transactions",
    )

    await db.commit()

    return {
        "bank_code": bank_code,
        "file_type": file_type,
        "file_name": file.filename,
        "transactions_found": len(transactions),
        "transactions": transactions[:100],  # Limit preview
    }


@router.get("/supported-banks")
async def list_supported_banks(
    admin: Profile = Depends(get_company_admin),
):
    """List banks that have registered statement parsing support."""
    from app.services.bank.registry import list_registered_providers
    providers = list_registered_providers()
    return {
        "banks": [
            {"code": code, "provider": name}
            for code, name in providers.items()
        ]
    }
