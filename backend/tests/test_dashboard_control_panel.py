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
