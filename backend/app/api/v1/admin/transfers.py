
"""Admin endpoints for contract/lot ownership transfers."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.database import get_db
from app.core.deps import get_company_admin, get_super_admin, require_permission
from app.models.client import Client
from app.models.contract_transfer import ContractTransfer
from app.models.enums import TransferStatus
from app.models.lot import Lot
from app.models.client_lot import ClientLot
from app.models.user import Profile
from app.schemas.contract_transfer import (
    ContractTransferApproveRequest,
    ContractTransferCompleteRequest,
    ContractTransferCreate,
    ContractTransferDetailResponse,
    ContractTransferResponse,
)
from app.services.transfer_service import (
    approve_transfer,
    cancel_transfer,
    complete_transfer,
    create_transfer,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/transfers", tags=["Admin Contract Transfers"])


@router.get("", response_model=list[ContractTransferDetailResponse])
async def list_transfers(
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_clients")),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List contract transfers with optional status filter."""
    stmt = select(ContractTransfer).where(ContractTransfer.company_id == admin.company_id)

    if status_filter:
        try:
            s = TransferStatus(status_filter.upper())
            stmt = stmt.where(ContractTransfer.status == s)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")

    stmt = stmt.order_by(ContractTransfer.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    transfers = result.scalars().all()

    responses = []
    for t in transfers:
        from_name = None
        to_name = None
        lot_identifier = None

        if t.from_client:
            from_name = t.from_client.full_name
        if t.to_client:
            to_name = t.to_client.full_name
        if t.client_lot:
            lot_row = await db.execute(select(Lot.block, Lot.number).where(Lot.id == t.client_lot.lot_id))
            lot_data = lot_row.one_or_none()
            if lot_data:
                lot_identifier = f"Qd {lot_data[0]} Lt {lot_data[1]}"

        resp = ContractTransferDetailResponse(
            **ContractTransferResponse.model_validate(t).model_dump(),
            from_client_name=from_name,
            to_client_name=to_name,
            lot_identifier=lot_identifier,
        )
        responses.append(resp)

    return responses


@router.post("", response_model=ContractTransferResponse, status_code=status.HTTP_201_CREATED)
async def create_transfer_endpoint(
    payload: ContractTransferCreate,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_clients")),
):
    """Create a new contract transfer request."""
    try:
        transfer = await create_transfer(
            db,
            company_id=admin.company_id,
            requested_by=admin.id,
            client_lot_id=payload.client_lot_id,
            from_client_id=payload.from_client_id,
            to_client_id=payload.to_client_id,
            transfer_fee=float(payload.transfer_fee) if payload.transfer_fee else None,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    await log_audit(
        db,
        user_id=admin.id,
        company_id=admin.company_id,
        table_name="contract_transfers",
        operation="CREATE",
        resource_id=str(transfer.id),
        detail=f"Transfer from {payload.from_client_id} to {payload.to_client_id}",
    )

    await db.commit()
    await db.refresh(transfer)
    return ContractTransferResponse.model_validate(transfer)


@router.get("/{transfer_id}", response_model=ContractTransferDetailResponse)
async def get_transfer(
    transfer_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_clients")),
):
    """Get a single transfer with details."""
    row = await db.execute(
        select(ContractTransfer).where(
            ContractTransfer.id == transfer_id,
            ContractTransfer.company_id == admin.company_id,
        )
    )
    t = row.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Transfer not found")

    from_name = t.from_client.full_name if t.from_client else None
    to_name = t.to_client.full_name if t.to_client else None
    lot_identifier = None
    if t.client_lot:
        lot_row = await db.execute(select(Lot.block, Lot.number).where(Lot.id == t.client_lot.lot_id))
        lot_data = lot_row.one_or_none()
        if lot_data:
            lot_identifier = f"Qd {lot_data[0]} Lt {lot_data[1]}"

    return ContractTransferDetailResponse(
        **ContractTransferResponse.model_validate(t).model_dump(),
        from_client_name=from_name,
        to_client_name=to_name,
        lot_identifier=lot_identifier,
    )


@router.post("/{transfer_id}/approve", response_model=ContractTransferResponse)
async def approve_transfer_endpoint(
    transfer_id: UUID,
    payload: ContractTransferApproveRequest,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_super_admin),
):
    """Approve a pending transfer (SUPER_ADMIN only)."""
    try:
        transfer = await approve_transfer(
            db,
            company_id=admin.company_id,
            transfer_id=transfer_id,
            approved_by=admin.id,
            admin_notes=payload.admin_notes,
            transfer_date=payload.transfer_date,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    await log_audit(
        db,
        user_id=admin.id,
        company_id=admin.company_id,
        table_name="contract_transfers",
        operation="APPROVE",
        resource_id=str(transfer_id),
    )

    await db.commit()
    await db.refresh(transfer)
    return ContractTransferResponse.model_validate(transfer)


@router.post("/{transfer_id}/complete", response_model=ContractTransferResponse)
async def complete_transfer_endpoint(
    transfer_id: UUID,
    payload: ContractTransferCompleteRequest,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_super_admin),
):
    """Complete an approved transfer — migrates lot, invoices, boletos (SUPER_ADMIN only)."""
    try:
        transfer = await complete_transfer(
            db,
            company_id=admin.company_id,
            transfer_id=transfer_id,
            performed_by=admin.id,
            admin_notes=payload.admin_notes,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    await log_audit(
        db,
        user_id=admin.id,
        company_id=admin.company_id,
        table_name="contract_transfers",
        operation="COMPLETE",
        resource_id=str(transfer_id),
    )

    await db.commit()
    await db.refresh(transfer)
    return ContractTransferResponse.model_validate(transfer)


@router.post("/{transfer_id}/cancel", response_model=ContractTransferResponse)
async def cancel_transfer_endpoint(
    transfer_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(require_permission("manage_clients")),
):
    """Cancel a pending or approved transfer."""
    try:
        transfer = await cancel_transfer(
            db,
            company_id=admin.company_id,
            transfer_id=transfer_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    await log_audit(
        db,
        user_id=admin.id,
        company_id=admin.company_id,
        table_name="contract_transfers",
        operation="CANCEL",
        resource_id=str(transfer_id),
    )

    await db.commit()
    await db.refresh(transfer)
    return ContractTransferResponse.model_validate(transfer)
