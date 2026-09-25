"""Dashboard as a control panel: the action queue and the billing pipeline."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.cycle_approval import CycleApproval
from app.models.enums import CycleApprovalStatus, InvoiceStatus
from app.models.invoice import Invoice
from app.models.user import Profile
from tests.conftest import auth_headers
from tests.test_cycle_approvals import _make_contract


@pytest.mark.asyncio
async def test_action_queue_surfaces_pending_cycles_with_instructions(
    client: AsyncClient, db_session: AsyncSession, test_company: Company, company_admin: Profile
):
    """A pending renewal must reach the dashboard, with a link and an instruction."""
    _, cl = await _make_contract(db_session, test_company, total_installments=24)
    db_session.add(
        CycleApproval(
            id=uuid.uuid4(), company_id=test_company.id, client_lot_id=cl.id,
            cycle_number=2, status=CycleApprovalStatus.PENDING,
            previous_installment_value=Decimal("1000.00"), unpaid_count=2,
        )
    )
    await db_session.flush()

    resp = await client.get(
        "/api/v1/admin/dashboard/action-queue", headers=auth_headers(company_admin)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    cycles = next(i for i in body["items"] if i["key"] == "cycle_approvals")
    assert cycles["count"] == 1
    assert cycles["severity"] == "critical"
    assert "Renovar agora" in cycles["hint"], "blocked renewals must say how to unblock"
    assert cycles["href"].startswith("/admin/cycle-approvals?status=PENDING")
    assert body["total"] >= 1

    # Every tile carries a destination and an instruction, not just a number.
    for item in body["items"]:
        assert item["href"], item["key"]
        assert item["hint"], item["key"]


@pytest.mark.asyncio
async def test_action_queue_flags_final_cycle_for_escrituracao(
    client: AsyncClient, db_session: AsyncSession, test_company: Company, company_admin: Profile
):
    _, cl = await _make_contract(db_session, test_company, total_installments=14)
    db_session.add(
        CycleApproval(
            id=uuid.uuid4(), company_id=test_company.id, client_lot_id=cl.id,
            cycle_number=2, status=CycleApprovalStatus.PENDING,
            previous_installment_value=Decimal("1000.00"), is_final_cycle=True,
        )
    )
    await db_session.flush()

    resp = await client.get(
        "/api/v1/admin/dashboard/action-queue", headers=auth_headers(company_admin)
    )
    assert resp.status_code == 200, resp.text
    final = next(
        i for i in resp.json()["items"] if i["key"] == "final_cycles"
    )
    assert final["count"] == 1
    assert "escrituração" in final["hint"].lower()


@pytest.mark.asyncio
async def test_billing_pipeline_counts_invoices_without_boleto(
    client: AsyncClient, db_session: AsyncSession, test_company: Company, company_admin: Profile
):
    """An installment with no boleto is the reason a cycle silently stalls."""
    _, cl = await _make_contract(db_session, test_company, total_installments=24)
    for i in range(3):
        db_session.add(
            Invoice(
                id=uuid.uuid4(),
                company_id=test_company.id,
                client_lot_id=cl.id,
                due_date=date.today() + timedelta(days=30 * i),
                amount=Decimal("1000.00"),
                installment_number=i + 1,
                status=InvoiceStatus.PENDING,
            )
        )
    await db_session.flush()

    resp = await client.get(
        "/api/v1/admin/dashboard/billing-pipeline", headers=auth_headers(company_admin)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["invoices_without_boleto"] == 3
    assert Decimal(body["invoices_without_boleto_amount"]) == Decimal("3000.00")


@pytest.mark.asyncio
async def test_dashboard_endpoints_are_company_scoped(
    client: AsyncClient,
    db_session: AsyncSession,
    test_company: Company,
    test_company_b: Company,
    company_admin_b: Profile,
):
    """Another company's pending renewal must not show on this dashboard."""
    _, cl = await _make_contract(db_session, test_company, total_installments=24)
    db_session.add(
        CycleApproval(
            id=uuid.uuid4(), company_id=test_company.id, client_lot_id=cl.id,
            cycle_number=2, status=CycleApprovalStatus.PENDING,
            previous_installment_value=Decimal("1000.00"),
        )
    )
    await db_session.flush()

    resp = await client.get(
        "/api/v1/admin/dashboard/action-queue", headers=auth_headers(company_admin_b)
    )
    assert resp.status_code == 200, resp.text
    cycles = next(i for i in resp.json()["items"] if i["key"] == "cycle_approvals")
    assert cycles["count"] == 0


@pytest.mark.asyncio
async def test_financial_overview_breaks_down_the_month(
    client: AsyncClient, db_session: AsyncSession, test_company: Company, company_admin: Profile
):
    """The month panel: target, cash in, still open, overdue, and next month.

    Lifetime totals never say whether the month is on track, which is what a
    revenue projection actually needs.
    """
    from datetime import datetime, timezone
    from dateutil.relativedelta import relativedelta

    _, cl = await _make_contract(db_session, test_company, total_installments=24)
    today = date.today()
    month_start = today.replace(day=1)
    next_month = month_start + relativedelta(months=1)

    def inv(due, amount, status, number, paid_at=None):
        return Invoice(
            id=uuid.uuid4(), company_id=test_company.id, client_lot_id=cl.id,
            due_date=due, amount=Decimal(amount), installment_number=number,
            status=status, paid_at=paid_at,
        )

    # Vencida neste mês e paga neste mês -> conta no previsto E no recebido.
    db_session.add(inv(month_start, "1000.00", InvoiceStatus.PAID, 1,
                       datetime.now(timezone.utc)))
    # Vencida neste mês, ainda em aberto e já passou -> atrasada do mês.
    db_session.add(inv(month_start, "500.00", InvoiceStatus.OVERDUE, 2))
    # Vence no fim deste mês, ainda a vencer -> aberta do mês.
    db_session.add(inv(next_month - timedelta(days=1), "700.00", InvoiceStatus.PENDING, 3))
    # Mês que vem -> só na projeção.
    db_session.add(inv(next_month + timedelta(days=5), "900.00", InvoiceStatus.PENDING, 4))
    await db_session.flush()

    resp = await client.get(
        "/api/v1/admin/dashboard/financial-overview", headers=auth_headers(company_admin)
    )
    assert resp.status_code == 200, resp.text
    b = resp.json()

    # Previsto do mês = tudo que vence no mês (1000 + 500 + 700)
    assert Decimal(b["month_expected_amount"]) == Decimal("2200.00")
    assert b["month_expected_count"] == 3
    # Caixa que entrou no mês
    assert Decimal(b["month_received_amount"]) == Decimal("1000.00")
    # Ainda a vencer dentro do mês
    assert Decimal(b["month_open_amount"]) == Decimal("700.00")
    # Vencida e não paga dentro do mês
    assert Decimal(b["month_overdue_amount"]) == Decimal("500.00")
    # Projeção do mês seguinte
    assert Decimal(b["next_month_expected_amount"]) == Decimal("900.00")
    assert b["next_month_expected_count"] == 1


@pytest.mark.asyncio
async def test_receivables_status_filter_accepts_any_casing(
    client: AsyncClient, db_session: AsyncSession, test_company: Company, company_admin: Profile
):
    """The Financeiro screen sends its filter lower-cased.

    Comparing the enum column against the raw string made Postgres reject it
    with `invalid input value for enum invoice_status: "pending"`, so every
    filter on that screen except "Todas" returned a 500.
    """
    for value in ("pending", "PENDING", "Overdue", "all"):
        resp = await client.get(
            f"/api/v1/admin/financial/receivables?status={value}",
            headers=auth_headers(company_admin),
        )
        assert resp.status_code == 200, f"{value} -> {resp.status_code}: {resp.text}"

    # An unknown value is a client error, reported as one.
    bad = await client.get(
        "/api/v1/admin/financial/receivables?status=xpto",
        headers=auth_headers(company_admin),
    )
    assert bad.status_code == 400, bad.text
    assert "PENDING" in bad.json()["detail"]

