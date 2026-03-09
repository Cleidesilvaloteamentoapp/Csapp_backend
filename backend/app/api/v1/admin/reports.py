
"""Admin endpoints for monthly reports and accounting exports."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, and_, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_company_admin
from app.models.client import Client
from app.models.client_lot import ClientLot
from app.models.contract_history import ContractHistory
from app.models.enums import (
    ClientLotStatus,
    ClientStatus,
    ContractEventType,
    InvoiceStatus,
    RescissionStatus,
)
from app.models.invoice import Invoice
from app.models.rescission import Rescission
from app.models.user import Profile

router = APIRouter(prefix="/reports", tags=["Admin Reports"])


@router.get("/monthly-closure")
async def monthly_closure(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Monthly closure report with financial summary, notifications, and cancellations.

    Returns data suitable for accounting: total collected, overdue amounts,
    notifications sent count, cancellations for tax write-offs.
    """
    cid = admin.company_id

    # Date range for the month
    month_start = date(year, month, 1)
    if month == 12:
        month_end = date(year + 1, 1, 1)
    else:
        month_end = date(year, month + 1, 1)

    # 1. Revenue collected in this month (paid invoices)
    paid_q = await db.execute(
        select(
            func.count(Invoice.id).label("count"),
            func.coalesce(func.sum(Invoice.amount), 0).label("total"),
        ).where(
            Invoice.company_id == cid,
            Invoice.status == InvoiceStatus.PAID,
            Invoice.paid_at >= datetime(year, month, 1, tzinfo=timezone.utc),
            Invoice.paid_at < datetime(
                month_end.year, month_end.month, month_end.day, tzinfo=timezone.utc
            ),
        )
    )
    paid_row = paid_q.one()
    paid_count = paid_row.count
    paid_total = Decimal(str(paid_row.total))

    # 2. Invoices generated this month
    generated_q = await db.execute(
        select(func.count(Invoice.id)).where(
            Invoice.company_id == cid,
            Invoice.due_date >= month_start,
            Invoice.due_date < month_end,
        )
    )
    generated_count = generated_q.scalar() or 0

    # 3. Overdue invoices as of month end
    overdue_q = await db.execute(
        select(
            func.count(Invoice.id).label("count"),
            func.coalesce(func.sum(Invoice.amount), 0).label("total"),
        ).where(
            Invoice.company_id == cid,
            Invoice.status == InvoiceStatus.OVERDUE,
            Invoice.due_date < month_end,
        )
    )
    overdue_row = overdue_q.one()
    overdue_count = overdue_row.count
    overdue_total = Decimal(str(overdue_row.total))

    # 4. Defaulters (clients in DEFAULTER status)
    defaulter_count_q = await db.execute(
        select(func.count(Client.id)).where(
            Client.company_id == cid,
            Client.status == ClientStatus.DEFAULTER,
        )
    )
    defaulter_count = defaulter_count_q.scalar() or 0

    # 5. Cancelled invoices this month (for tax write-offs)
    cancelled_q = await db.execute(
        select(
            func.count(Invoice.id).label("count"),
            func.coalesce(func.sum(Invoice.amount), 0).label("total"),
        ).where(
            Invoice.company_id == cid,
            Invoice.status == InvoiceStatus.CANCELLED,
            Invoice.updated_at >= datetime(year, month, 1, tzinfo=timezone.utc),
            Invoice.updated_at < datetime(
                month_end.year, month_end.month, month_end.day, tzinfo=timezone.utc
            ),
        )
    )
    cancelled_row = cancelled_q.one()
    cancelled_count = cancelled_row.count
    cancelled_total = Decimal(str(cancelled_row.total))

    # 6. Rescissions completed this month
    rescission_q = await db.execute(
        select(func.count(Rescission.id)).where(
            Rescission.company_id == cid,
            Rescission.status == RescissionStatus.COMPLETED,
            Rescission.completion_date >= month_start,
            Rescission.completion_date < month_end,
        )
    )
    rescission_count = rescission_q.scalar() or 0

    # 7. Notifications sent this month (from contract_history)
    notification_q = await db.execute(
        select(func.count(ContractHistory.id)).where(
            ContractHistory.company_id == cid,
            ContractHistory.event_type.in_([
                ContractEventType.OVERDUE,
                ContractEventType.STATUS_CHANGE,
                ContractEventType.SECOND_COPY,
            ]),
            ContractHistory.created_at >= datetime(year, month, 1, tzinfo=timezone.utc),
            ContractHistory.created_at < datetime(
                month_end.year, month_end.month, month_end.day, tzinfo=timezone.utc
            ),
        )
    )
    notification_count = notification_q.scalar() or 0

    # 8. Renegotiations applied this month
    from app.models.renegotiation import Renegotiation
    from app.models.enums import RenegotiationStatus
    renego_q = await db.execute(
        select(
            func.count(Renegotiation.id).label("count"),
            func.coalesce(func.sum(Renegotiation.final_amount), 0).label("total"),
        ).where(
            Renegotiation.company_id == cid,
            Renegotiation.status == RenegotiationStatus.APPLIED,
            Renegotiation.applied_at >= datetime(year, month, 1, tzinfo=timezone.utc),
            Renegotiation.applied_at < datetime(
                month_end.year, month_end.month, month_end.day, tzinfo=timezone.utc
            ),
        )
    )
    renego_row = renego_q.one()

    return {
        "period": f"{year}-{month:02d}",
        "company_id": str(cid),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "revenue": {
            "invoices_paid_count": paid_count,
            "invoices_paid_total": float(paid_total),
        },
        "invoices_generated": generated_count,
        "overdue": {
            "count": overdue_count,
            "total": float(overdue_total),
        },
        "defaulters_count": defaulter_count,
        "cancellations": {
            "invoices_cancelled_count": cancelled_count,
            "invoices_cancelled_total": float(cancelled_total),
            "rescissions_completed": rescission_count,
        },
        "renegotiations": {
            "applied_count": renego_row.count,
            "applied_total": float(Decimal(str(renego_row.total))),
        },
        "notifications_sent": notification_count,
    }


@router.get("/monthly-closure/csv")
async def monthly_closure_csv(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Export paid invoices for a given month as CSV for accounting."""
    import csv
    import io

    cid = admin.company_id
    month_start = date(year, month, 1)
    if month == 12:
        month_end = date(year + 1, 1, 1)
    else:
        month_end = date(year, month + 1, 1)

    rows = await db.execute(
        select(Invoice, Client.full_name, Client.cpf_cnpj)
        .join(ClientLot, ClientLot.id == Invoice.client_lot_id)
        .join(Client, Client.id == ClientLot.client_id)
        .where(
            Invoice.company_id == cid,
            Invoice.status == InvoiceStatus.PAID,
            Invoice.paid_at >= datetime(year, month, 1, tzinfo=timezone.utc),
            Invoice.paid_at < datetime(
                month_end.year, month_end.month, month_end.day, tzinfo=timezone.utc
            ),
        )
        .order_by(Invoice.paid_at)
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "invoice_id", "client_name", "cpf_cnpj", "installment_number",
        "due_date", "paid_at", "amount", "status"
    ])

    for inv, client_name, cpf_cnpj in rows.all():
        writer.writerow([
            str(inv.id),
            client_name,
            cpf_cnpj,
            inv.installment_number,
            inv.due_date.isoformat(),
            inv.paid_at.isoformat() if inv.paid_at else "",
            str(inv.amount),
            inv.status.value,
        ])

    output.seek(0)
    filename = f"relatorio_mensal_{year}_{month:02d}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/cancellations/csv")
async def cancellations_csv(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    admin: Profile = Depends(get_company_admin),
):
    """Export cancelled invoices and rescissions for tax write-offs."""
    import csv
    import io

    cid = admin.company_id
    month_start = date(year, month, 1)
    if month == 12:
        month_end = date(year + 1, 1, 1)
    else:
        month_end = date(year, month + 1, 1)

    # Cancelled invoices
    rows = await db.execute(
        select(Invoice, Client.full_name, Client.cpf_cnpj)
        .join(ClientLot, ClientLot.id == Invoice.client_lot_id)
        .join(Client, Client.id == ClientLot.client_id)
        .where(
            Invoice.company_id == cid,
            Invoice.status == InvoiceStatus.CANCELLED,
            Invoice.updated_at >= datetime(year, month, 1, tzinfo=timezone.utc),
            Invoice.updated_at < datetime(
                month_end.year, month_end.month, month_end.day, tzinfo=timezone.utc
            ),
        )
        .order_by(Invoice.updated_at)
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "type", "id", "client_name", "cpf_cnpj",
        "original_amount", "date", "reason"
    ])

    for inv, client_name, cpf_cnpj in rows.all():
        writer.writerow([
            "INVOICE_CANCELLED",
            str(inv.id),
            client_name,
            cpf_cnpj,
            str(inv.amount),
            inv.updated_at.isoformat() if inv.updated_at else "",
            "Cancelamento de boleto",
        ])

    # Rescissions
    resc_rows = await db.execute(
        select(Rescission, Client.full_name, Client.cpf_cnpj)
        .join(Client, Client.id == Rescission.client_id)
        .where(
            Rescission.company_id == cid,
            Rescission.status == RescissionStatus.COMPLETED,
            Rescission.completion_date >= month_start,
            Rescission.completion_date < month_end,
        )
    )
    for resc, client_name, cpf_cnpj in resc_rows.all():
        writer.writerow([
            "RESCISSION",
            str(resc.id),
            client_name,
            cpf_cnpj,
            str(resc.total_debt),
            resc.completion_date.isoformat() if resc.completion_date else "",
            resc.reason or "Rescisão contratual",
        ])

    output.seek(0)
    filename = f"cancelamentos_{year}_{month:02d}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
