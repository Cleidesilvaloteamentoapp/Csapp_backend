
"""Celery tasks for index-based contract adjustment and admin alerts.

Adjustments run per the contract's frequency (monthly / quarterly / semiannual /
annual). Each cycle's installments must be fully paid before the next cycle's
value is recalculated as index %% + fixed rate.
"""

from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from app.tasks._async_helpers import TaskSessionFactory, run_in_task_loop
from app.tasks.celery_app import celery
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Installments per adjustment cycle, keyed by AdjustmentFrequency.value.
_CYCLE_SIZE = {"MONTHLY": 1, "QUARTERLY": 3, "SEMIANNUAL": 6, "ANNUAL": 12}
# Minimum months that must elapse between adjustments, keyed the same way.
_MIN_MONTHS = {"MONTHLY": 1, "QUARTERLY": 3, "SEMIANNUAL": 6, "ANNUAL": 12}


async def _apply_annual_adjustments_async(session_factory: TaskSessionFactory):
    """Apply per-lot index + fixed rate adjustments to active contracts.

    Each contract can use a different index (IPCA, IGPM, CUB, INPC) and custom
    fixed rate, configured via client_lot.adjustment_index and
    client_lot.adjustment_custom_rate.

    Default: IPCA + 5% fixed rate.
    Only applies to contracts where the last 12-installment cycle is fully paid.
    """
    from sqlalchemy import select
    from app.models.client_lot import ClientLot
    from app.models.enums import ClientLotStatus, ContractEventType, InvoiceStatus
    from app.models.invoice import Invoice
    from app.services.contract_history_service import record_event
    from app.services.index_service import get_accumulated_index, calculate_adjusted_value

    today = date.today()

    async with session_factory() as db:
        # Candidate contracts: never adjusted, or last adjusted at least a month
        # ago (the loosest frequency). The exact interval is checked per contract.
        one_month_ago = today - relativedelta(months=1)
        rows = await db.execute(
            select(ClientLot).where(
                ClientLot.status == ClientLotStatus.ACTIVE,
                ClientLot.last_adjustment_date.is_(None) | (ClientLot.last_adjustment_date <= one_month_ago),
            )
        )
        contracts = rows.scalars().all()
        adjusted_count = 0
        skipped_no_index = 0

        # Cache index values per (index_type, company_id) to avoid repeated API calls
        index_cache: dict[tuple, Decimal] = {}

        from app.services.financial_defaults_service import (
            get_effective_adjustment_index, get_effective_adjustment_frequency,
            get_effective_custom_rate,
        )

        for cl in contracts:
            # Resolve the contract's adjustment frequency and the matching cycle.
            frequency = await get_effective_adjustment_frequency(db, cl)
            cycle_size = _CYCLE_SIZE.get(frequency.value, 12)
            min_months = _MIN_MONTHS.get(frequency.value, 12)

            # Enforce the minimum interval for this specific frequency.
            if cl.last_adjustment_date and cl.last_adjustment_date > today - relativedelta(months=min_months):
                continue

            # Cycle lock: the last `cycle_size` invoices must all be PAID.
            recent_invoices = await db.execute(
                select(Invoice)
                .where(
                    Invoice.client_lot_id == cl.id,
                    Invoice.status != InvoiceStatus.CANCELLED,
                )
                .order_by(Invoice.installment_number.desc())
                .limit(cycle_size)
            )
            recent = list(recent_invoices.scalars().all())

            if len(recent) < cycle_size:
                continue
            all_paid = all(inv.status == InvoiceStatus.PAID for inv in recent)
            if not all_paid:
                continue

            # Determine which index to use (3-tier: per-lot → company → IPCA)
            index_type = await get_effective_adjustment_index(db, cl)

            # A per-contract manual index value (e.g. IPCA do dia) overrides the lookup.
            if cl.manual_index_value is not None:
                index_pct = Decimal(str(cl.manual_index_value))
            else:
                cache_key = (index_type, cl.company_id)
                if cache_key not in index_cache:
                    index_cache[cache_key] = await get_accumulated_index(
                        index_type,
                        reference_date=today,
                        db=db,
                        company_id=cl.company_id,
                    )
                index_pct = index_cache[cache_key]

            if index_pct <= 0:
                skipped_no_index += 1
                logger.warning("adjustment_skipped_no_index", cl_id=str(cl.id), index=index_type.value)
                continue

            # Calculate adjustment using 3-tier custom rate
            current_value = cl.current_installment_value or (cl.total_value / cl.total_installments)
            effective_custom_rate = await get_effective_custom_rate(db, cl)
            fixed_rate_pct = Decimal(str(effective_custom_rate * 100))

            adj = calculate_adjusted_value(current_value, index_pct, fixed_rate_pct)

            # Update contract
            cl.current_installment_value = adj["new_value"]
            cl.last_adjustment_date = today
            cl.current_cycle += 1
            cl.last_cycle_paid_at = today

            await record_event(
                db,
                company_id=cl.company_id,
                client_id=cl.client_id,
                client_lot_id=cl.id,
                event_type=ContractEventType.ADJUSTMENT,
                description=(
                    f"Reajuste {frequency.value.lower()} aplicado (ciclo {cl.current_cycle}). "
                    f"Índice: {index_type.value} {index_pct}%"
                    f"{' (manual)' if cl.manual_index_value is not None else ''}, "
                    f"Taxa fixa: {fixed_rate_pct}%. "
                    f"Valor anterior: R${adj['original_value']}, "
                    f"Novo valor: R${adj['new_value']}"
                ),
                amount=adj["new_value"],
                previous_value=str(adj["original_value"]),
                new_value=str(adj["new_value"]),
                metadata_json={
                    "index_type": index_type.value,
                    "frequency": frequency.value,
                    "manual_index": cl.manual_index_value is not None,
                    "index_pct": str(index_pct),
                    "fixed_rate_pct": str(fixed_rate_pct),
                    "index_adjustment": str(adj["index_adjustment"]),
                    "fixed_adjustment": str(adj["fixed_adjustment"]),
                    "cycle": cl.current_cycle,
                },
            )

            adjusted_count += 1
            logger.info(
                "contract_adjusted",
                client_lot_id=str(cl.id),
                index=index_type.value,
                old_value=str(adj["original_value"]),
                new_value=str(adj["new_value"]),
            )

        await db.commit()
        logger.info(
            "annual_adjustments_completed",
            count=adjusted_count,
            skipped_no_index=skipped_no_index,
        )


@celery.task(bind=True, max_retries=3, default_retry_delay=600)
def apply_annual_adjustments(self):
    """Annual task: apply IPCA + fixed rate adjustment to eligible contracts."""
    try:
        run_in_task_loop(_apply_annual_adjustments_async)
    except Exception as exc:
        logger.error("annual_adjustment_failed", error=str(exc))
        self.retry(exc=exc)


async def _send_admin_alerts_async(session_factory: TaskSessionFactory):
    """Send admin alerts for cycle completions and critical defaulters."""
    from sqlalchemy import select, func
    from app.models.client import Client
    from app.models.client_lot import ClientLot
    from app.models.enums import ClientLotStatus, ClientStatus, InvoiceStatus
    from app.models.invoice import Invoice
    from app.services.email_service import send_admin_alert

    today = date.today()
    ninety_days_ago = today - timedelta(days=90)

    async with session_factory() as db:
        # Alert 1: Clients with 90+ days overdue (rescission trigger)
        critical_rows = await db.execute(
            select(Client.id, Client.full_name, Client.company_id, func.min(Invoice.due_date).label("oldest_due"))
            .join(ClientLot, ClientLot.client_id == Client.id)
            .join(Invoice, Invoice.client_lot_id == ClientLot.id)
            .where(
                Client.status == ClientStatus.DEFAULTER,
                Invoice.status == InvoiceStatus.OVERDUE,
                Invoice.due_date <= ninety_days_ago,
            )
            .group_by(Client.id, Client.full_name, Client.company_id)
        )
        critical_clients = critical_rows.all()
        for row in critical_clients:
            days = (today - row.oldest_due).days
            try:
                await send_admin_alert(
                    company_id=str(row.company_id),
                    subject=f"ALERTA: Cliente {row.full_name} com {days} dias de atraso",
                    message=(
                        f"O cliente {row.full_name} está com {days} dias de inadimplência. "
                        f"De acordo com a política, contratos com 90+ dias de atraso "
                        f"devem iniciar processo de rescisão."
                    ),
                    db=db,
                )
            except Exception as exc:
                logger.warning("admin_alert_failed", client_id=str(row.id), error=str(exc))

        # Alert 2: Clients who completed a 12-invoice cycle
        cycle_complete_rows = await db.execute(
            select(
                ClientLot.id.label("cl_id"),
                ClientLot.company_id,
                ClientLot.current_cycle,
                Client.full_name,
            )
            .join(Client, Client.id == ClientLot.client_id)
            .where(ClientLot.status == ClientLotStatus.ACTIVE)
        )
        for row in cycle_complete_rows.all():
            # Check if last 12 invoices all paid
            inv_rows = await db.execute(
                select(Invoice)
                .where(Invoice.client_lot_id == row.cl_id)
                .order_by(Invoice.installment_number.desc())
                .limit(12)
            )
            recent = list(inv_rows.scalars().all())
            if len(recent) == 12 and all(inv.status == InvoiceStatus.PAID for inv in recent):
                # Check if the most recent was paid in the last 7 days (avoid repeat alerts)
                last_paid = max((inv.paid_at for inv in recent if inv.paid_at), default=None)
                if last_paid and (today - last_paid.date()).days <= 7:
                    try:
                        await send_admin_alert(
                            company_id=str(row.company_id),
                            subject=f"Ciclo {row.current_cycle} concluído: {row.full_name}",
                            message=(
                                f"O cliente {row.full_name} completou o ciclo {row.current_cycle} "
                                f"de 12 parcelas. Reajuste anual deve ser aplicado."
                            ),
                            db=db,
                        )
                    except Exception as exc:
                        logger.warning("cycle_alert_failed", cl_id=str(row.cl_id), error=str(exc))

        logger.info("admin_alerts_completed", date=today.isoformat())


@celery.task(bind=True, max_retries=3, default_retry_delay=300)
def send_admin_alerts(self):
    """Daily task: send admin alerts for critical situations."""
    try:
        run_in_task_loop(_send_admin_alerts_async)
    except Exception as exc:
        logger.error("admin_alerts_failed", error=str(exc))
        self.retry(exc=exc)
