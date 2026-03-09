
"""Admin endpoints for boleto management (database records).

Provides CRUD operations for persisted boleto records:
- List all boletos with filters (client, status, date range)
- Get boleto details by ID or nossoNumero
- Update boleto status (e.g., after payment confirmation)
- List boletos by client
"""

from typing import Optional
from uuid import UUID
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import get_company_admin
from app.models.user import Profile
from app.models.boleto import Boleto
from app.models.client import Client
from app.models.enums import BoletoStatus
from app.schemas.boleto import (
    BoletoResponse,
    BoletoListResponse,
    BoletoWithClientResponse,
    BoletoUpdateRequest,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/boletos", tags=["Admin Boletos"])


# ---------------------------------------------------------------------------
# List & Filters
# ---------------------------------------------------------------------------

@router.get("", response_model=list[BoletoWithClientResponse])
async def list_boletos(
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
    client_id: Optional[UUID] = Query(None, description="Filter by client UUID"),
    status: Optional[str] = Query(None, description="Filter by status: NORMAL, LIQUIDADO, VENCIDO, CANCELADO"),
    data_vencimento_inicio: Optional[date] = Query(None, description="Filter by due date start (YYYY-MM-DD)"),
    data_vencimento_fim: Optional[date] = Query(None, description="Filter by due date end (YYYY-MM-DD)"),
    seu_numero: Optional[str] = Query(None, description="Search by seu_numero (internal control number)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List all boletos with optional filters."""
    
    stmt = select(Boleto).where(Boleto.company_id == admin.company_id)
    
    if client_id:
        stmt = stmt.where(Boleto.client_id == client_id)
    
    if status:
        try:
            status_enum = BoletoStatus(status.upper())
            stmt = stmt.where(Boleto.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    
    if data_vencimento_inicio:
        stmt = stmt.where(Boleto.data_vencimento >= data_vencimento_inicio)
    
    if data_vencimento_fim:
        stmt = stmt.where(Boleto.data_vencimento <= data_vencimento_fim)
    
    if seu_numero:
        stmt = stmt.where(Boleto.seu_numero.ilike(f"%{seu_numero}%"))
    
    stmt = stmt.options(selectinload(Boleto.client))
    stmt = stmt.order_by(Boleto.created_at.desc())
    stmt = stmt.limit(limit).offset(offset)
    
    result = await db.execute(stmt)
    boletos = result.scalars().all()
    
    response = []
    for boleto in boletos:
        boleto_dict = {
            "id": boleto.id,
            "nosso_numero": boleto.nosso_numero,
            "seu_numero": boleto.seu_numero,
            "linha_digitavel": boleto.linha_digitavel,
            "codigo_barras": boleto.codigo_barras,
            "tipo_cobranca": boleto.tipo_cobranca,
            "data_vencimento": boleto.data_vencimento,
            "data_emissao": boleto.data_emissao,
            "data_liquidacao": boleto.data_liquidacao,
            "valor": boleto.valor,
            "valor_liquidacao": boleto.valor_liquidacao,
            "status": boleto.status.value,
            "txid": boleto.txid,
            "qr_code": boleto.qr_code,
            "created_at": boleto.created_at,
            "updated_at": boleto.updated_at,
            "client": {
                "id": boleto.client.id,
                "full_name": boleto.client.full_name,
                "cpf_cnpj": boleto.client.cpf_cnpj,
                "email": boleto.client.email,
                "phone": boleto.client.phone,
            } if boleto.client else None
        }
        response.append(BoletoWithClientResponse(**boleto_dict))
    
    return response


@router.get("/stats")
async def get_boleto_stats(
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Get boleto statistics dashboard data."""
    
    # Total count by status
    stmt = select(
        Boleto.status,
        func.count(Boleto.id).label("count"),
        func.sum(Boleto.valor).label("total_value")
    ).where(
        Boleto.company_id == admin.company_id
    ).group_by(Boleto.status)
    
    result = await db.execute(stmt)
    status_stats = result.all()
    
    stats = {
        "by_status": [
            {
                "status": row.status.value,
                "count": row.count,
                "total_value": float(row.total_value or 0)
            }
            for row in status_stats
        ]
    }
    
    # Overdue boletos (vencidos e não pagos)
    today = date.today()
    stmt = select(func.count(Boleto.id)).where(
        and_(
            Boleto.company_id == admin.company_id,
            Boleto.data_vencimento < today,
            Boleto.status.in_([BoletoStatus.NORMAL, BoletoStatus.VENCIDO])
        )
    )
    result = await db.execute(stmt)
    overdue_count = result.scalar()
    
    stats["overdue_count"] = overdue_count
    
    return stats


# ---------------------------------------------------------------------------
# Get by ID or nossoNumero
# ---------------------------------------------------------------------------

@router.get("/id/{boleto_id}", response_model=BoletoResponse)
async def get_boleto_by_id(
    boleto_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Get full boleto details by database ID."""
    
    stmt = select(Boleto).where(
        Boleto.id == boleto_id,
        Boleto.company_id == admin.company_id
    ).options(selectinload(Boleto.client))
    
    result = await db.execute(stmt)
    boleto = result.scalar_one_or_none()
    
    if not boleto:
        raise HTTPException(status_code=404, detail="Boleto not found")
    
    return BoletoResponse.model_validate(boleto)


@router.get("/nosso-numero/{nosso_numero}", response_model=BoletoResponse)
async def get_boleto_by_nosso_numero(
    nosso_numero: str,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Get full boleto details by nossoNumero."""
    
    stmt = select(Boleto).where(
        Boleto.nosso_numero == nosso_numero,
        Boleto.company_id == admin.company_id
    ).options(selectinload(Boleto.client))
    
    result = await db.execute(stmt)
    boleto = result.scalar_one_or_none()
    
    if not boleto:
        raise HTTPException(status_code=404, detail="Boleto not found")
    
    return BoletoResponse.model_validate(boleto)


# ---------------------------------------------------------------------------
# List by Client
# ---------------------------------------------------------------------------

@router.get("/client/{client_id}", response_model=list[BoletoListResponse])
async def list_boletos_by_client(
    client_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
    status: Optional[str] = Query(None, description="Filter by status"),
):
    """List all boletos for a specific client."""
    
    # Verify client belongs to company
    stmt_client = select(Client).where(
        Client.id == client_id,
        Client.company_id == admin.company_id
    )
    result = await db.execute(stmt_client)
    client = result.scalar_one_or_none()
    
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    stmt = select(Boleto).where(
        Boleto.client_id == client_id,
        Boleto.company_id == admin.company_id
    )
    
    if status:
        try:
            status_enum = BoletoStatus(status.upper())
            stmt = stmt.where(Boleto.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    
    stmt = stmt.order_by(Boleto.data_vencimento.desc())
    
    result = await db.execute(stmt)
    boletos = result.scalars().all()
    
    return [BoletoListResponse.model_validate(b) for b in boletos]


# ---------------------------------------------------------------------------
# Update boleto status
# ---------------------------------------------------------------------------

@router.patch("/{boleto_id}", response_model=BoletoResponse)
async def update_boleto(
    boleto_id: UUID,
    payload: BoletoUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Update boleto fields (status, payment info)."""
    
    stmt = select(Boleto).where(
        Boleto.id == boleto_id,
        Boleto.company_id == admin.company_id
    )
    
    result = await db.execute(stmt)
    boleto = result.scalar_one_or_none()
    
    if not boleto:
        raise HTTPException(status_code=404, detail="Boleto not found")
    
    update_data = payload.model_dump(exclude_none=True)
    
    for key, value in update_data.items():
        if key == "status":
            setattr(boleto, key, BoletoStatus(value))
        else:
            setattr(boleto, key, value)
    
    await db.commit()
    await db.refresh(boleto)
    
    logger.info(f"Boleto {boleto.nosso_numero} updated by admin {admin.id}")
    
    return BoletoResponse.model_validate(boleto)


# ---------------------------------------------------------------------------
# Delete boleto (soft delete via status = CANCELADO)
# ---------------------------------------------------------------------------

@router.delete("/{boleto_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_boleto(
    boleto_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Soft delete boleto by setting status to CANCELADO."""
    
    stmt = select(Boleto).where(
        Boleto.id == boleto_id,
        Boleto.company_id == admin.company_id
    )
    
    result = await db.execute(stmt)
    boleto = result.scalar_one_or_none()
    
    if not boleto:
        raise HTTPException(status_code=404, detail="Boleto not found")
    
    boleto.status = BoletoStatus.CANCELADO
    await db.commit()
    
    logger.info(f"Boleto {boleto.nosso_numero} cancelled by admin {admin.id}")
