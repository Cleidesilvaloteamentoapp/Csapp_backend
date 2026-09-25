"""Cycle renewal: the approval gate, the forced override and the final cycle.

These cover the chain that was silently broken in production: a batch boleto
that carried no invoice_id meant settlement never reached the invoice, so no
CycleApproval was ever raised and the panel stayed empty forever.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.boleto import Boleto
from app.models.client import Client
from app.models.client_lot import ClientLot
from app.models.company import Company
from app.models.cycle_approval import CycleApproval
from app.models.deed_checklist import DeedChecklist
from app.models.development import Development
from app.models.enums import (
    BoletoStatus,
    ClientLotStatus,
    ClientStatus,
    CycleApprovalStatus,
    InvoiceStatus,
    LotStatus,
)
from app.models.invoice import Invoice
from app.models.lot import Lot
from app.models.user import Profile
from tests.conftest import auth_headers


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

async def _make_contract(
    db: AsyncSession,
    company: Company,
    *,
    total_installments: int,
    current_cycle: int = 1,
    installment_value: Decimal = Decimal("1000.00"),
) -> tuple[Client, ClientLot]:
    client = Client(
        id=uuid.uuid4(),
        company_id=company.id,
        email=f"c{uuid.uuid4().hex[:8]}@test.com",
        full_name="Cliente Teste",
        cpf_cnpj=uuid.uuid4().hex[:11],
        phone="11988887777",
        status=ClientStatus.ACTIVE,
        address={
            "street": "Rua A",
            "number": "100",
            "city": "Curitiba",
            "state": "PR",
            "zip": "80000000",
        },
    )
    dev = Development(id=uuid.uuid4(), company_id=company.id, name="Loteamento")
    db.add_all([client, dev])
    await db.flush()

    lot = Lot(
        id=uuid.uuid4(),
        company_id=company.id,
        development_id=dev.id,
        block="A",
        lot_number="1",
        area_m2=Decimal("250.00"),
        price=Decimal("100000.00"),
        status=LotStatus.SOLD,
    )
    db.add(lot)
    await db.flush()

    cl = ClientLot(
        id=uuid.uuid4(),
        company_id=company.id,
        client_id=client.id,
        lot_id=lot.id,
        purchase_date=date.today() - timedelta(days=365),
        total_value=installment_value * total_installments,
        total_installments=total_installments,
        current_cycle=current_cycle,
        current_installment_value=installment_value,
        status=ClientLotStatus.ACTIVE,
    )
    db.add(cl)
    await db.flush()
    return client, cl


async def _add_invoices(
    db: AsyncSession,
    company: Company,
    cl: ClientLot,
    *,
    first_number: int,
    count: int,
    first_due: date,
    settled: int = 0,
    amount: Decimal = Decimal("1000.00"),
) -> list[Invoice]:
    """Create `count` invoices; the first `settled` are PAID with a LIQUIDADO boleto."""
    made = []
    for i in range(count):
        inv = Invoice(
            id=uuid.uuid4(),
            company_id=company.id,
            client_lot_id=cl.id,
            due_date=first_due + timedelta(days=30 * i),
            amount=amount,
            installment_number=first_number + i,
            status=InvoiceStatus.PENDING,
        )
        db.add(inv)
        made.append(inv)
    await db.flush()

    for inv in made[:settled]:
        inv.status = InvoiceStatus.PAID
        inv.paid_at = datetime.now(timezone.utc)
        db.add(
            Boleto(
                id=uuid.uuid4(),
                company_id=company.id,
                client_id=cl.client_id,
                invoice_id=inv.id,
                nosso_numero=uuid.uuid4().hex[:10],
                seu_numero=uuid.uuid4().hex[:10],
                tipo_cobranca="HIBRIDO",
                especie_documento="DUPLICATA_MERCANTIL_INDICACAO",
                data_vencimento=inv.due_date,
                data_emissao=inv.due_date - timedelta(days=30),
                valor=inv.amount,
                status=BoletoStatus.LIQUIDADO,
            )
        )
    await db.flush()
    return made


# ---------------------------------------------------------------------------
# The approval gate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_approve_blocked_while_cycle_unpaid(
    client: AsyncClient, db_session: AsyncSession, test_company: Company, company_admin: Profile
):
    """Approve refuses with 409 while the closing cycle has open installments."""
    _, cl = await _make_contract(db_session, test_company, total_installments=24)
    await _add_invoices(
        db_session, test_company, cl,
        first_number=1, count=12, first_due=date.today() - timedelta(days=300), settled=10,
    )
    ap = CycleApproval(
        id=uuid.uuid4(), company_id=test_company.id, client_lot_id=cl.id,
        cycle_number=2, status=CycleApprovalStatus.PENDING,
        previous_installment_value=Decimal("1000.00"), unpaid_count=2,
    )
    db_session.add(ap)
    await db_session.flush()

    resp = await client.post(
        f"/api/v1/admin/cycle-approvals/{ap.id}/approve",
        json={"new_installment_value": "1050.00"},
        headers=auth_headers(company_admin),
    )
    assert resp.status_code == 409, resp.text
    assert "Renovar agora" in resp.json()["detail"]

    await db_session.refresh(ap)
    assert ap.status == CycleApprovalStatus.PENDING


@pytest.mark.asyncio
async def test_force_approve_releases_with_justification(
    client: AsyncClient, db_session: AsyncSession, test_company: Company, company_admin: Profile
):
    """Renovar agora releases the next cycle and records who forced it and why."""
    _, cl = await _make_contract(db_session, test_company, total_installments=24)
    await _add_invoices(
        db_session, test_company, cl,
        first_number=1, count=12, first_due=date.today() - timedelta(days=300), settled=10,
    )
    ap = CycleApproval(
        id=uuid.uuid4(), company_id=test_company.id, client_lot_id=cl.id,
        cycle_number=2, status=CycleApprovalStatus.PENDING,
        previous_installment_value=Decimal("1000.00"), unpaid_count=2,
    )
    db_session.add(ap)
    await db_session.flush()

    resp = await client.post(
        f"/api/v1/admin/cycle-approvals/{ap.id}/force-approve",
        json={
            "new_installment_value": "1050.00",
            "justification": "Cliente renegociou as duas parcelas em aberto na agência.",
        },
        headers=auth_headers(company_admin),
    )
    assert resp.status_code == 200, resp.text

    await db_session.refresh(ap)
    assert ap.status == CycleApprovalStatus.APPROVED
    assert ap.forced is True
    assert ap.forced_by == company_admin.id
    assert "renegociou" in ap.forced_reason

    rows = await db_session.execute(
        select(Invoice).where(
            Invoice.client_lot_id == cl.id, Invoice.installment_number > 12
        )
    )
    new_invoices = rows.scalars().all()
    assert len(new_invoices) == 12
    assert {i.amount for i in new_invoices} == {Decimal("1050.00")}


@pytest.mark.asyncio
async def test_force_approve_requires_long_justification(
    client: AsyncClient, db_session: AsyncSession, test_company: Company, company_admin: Profile
):
    """A one-word reason is not an audit trail."""
    _, cl = await _make_contract(db_session, test_company, total_installments=24)
    await _add_invoices(
        db_session, test_company, cl,
        first_number=1, count=12, first_due=date.today() - timedelta(days=300), settled=10,
    )
    ap = CycleApproval(
        id=uuid.uuid4(), company_id=test_company.id, client_lot_id=cl.id,
        cycle_number=2, status=CycleApprovalStatus.PENDING,
        previous_installment_value=Decimal("1000.00"),
    )
    db_session.add(ap)
    await db_session.flush()

    resp = await client.post(
        f"/api/v1/admin/cycle-approvals/{ap.id}/force-approve",
        json={"new_installment_value": "1050.00", "justification": "ok"},
        headers=auth_headers(company_admin),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_approve_succeeds_when_cycle_fully_settled(
    client: AsyncClient, db_session: AsyncSession, test_company: Company, company_admin: Profile
):
    """The happy path: everything liquidado, approve releases the next 12."""
    _, cl = await _make_contract(db_session, test_company, total_installments=24)
    await _add_invoices(
        db_session, test_company, cl,
        first_number=1, count=12, first_due=date.today() - timedelta(days=300), settled=12,
    )
    ap = CycleApproval(
        id=uuid.uuid4(), company_id=test_company.id, client_lot_id=cl.id,
        cycle_number=2, status=CycleApprovalStatus.PENDING,
        previous_installment_value=Decimal("1000.00"),
    )
    db_session.add(ap)
    await db_session.flush()

    resp = await client.post(
        f"/api/v1/admin/cycle-approvals/{ap.id}/approve",
        json={"new_installment_value": "1080.00"},
        headers=auth_headers(company_admin),
    )
    assert resp.status_code == 200, resp.text

    await db_session.refresh(cl)
    assert cl.current_cycle == 2
    assert cl.current_installment_value == Decimal("1080.00")


# ---------------------------------------------------------------------------
# The short final cycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_final_cycle_generates_remainder_and_opens_deed_checklist(
    client: AsyncClient, db_session: AsyncSession, test_company: Company, company_admin: Profile
):
    """A 14-installment contract ends on a cycle of 2, not a refusal.

    The old gate bailed out whenever fewer than 12 installments remained, so the
    last cycle of any contract that was not a multiple of 12 could never be
    released.
    """
    _, cl = await _make_contract(db_session, test_company, total_installments=14)
    await _add_invoices(
        db_session, test_company, cl,
        first_number=1, count=12, first_due=date.today() - timedelta(days=300), settled=12,
    )
    ap = CycleApproval(
        id=uuid.uuid4(), company_id=test_company.id, client_lot_id=cl.id,
        cycle_number=2, status=CycleApprovalStatus.PENDING,
        previous_installment_value=Decimal("1000.00"),
    )
    db_session.add(ap)
    await db_session.flush()

    resp = await client.post(
        f"/api/v1/admin/cycle-approvals/{ap.id}/approve",
        json={"new_installment_value": "1050.00"},
        headers=auth_headers(company_admin),
    )
    assert resp.status_code == 200, resp.text

    rows = await db_session.execute(
        select(Invoice).where(
            Invoice.client_lot_id == cl.id, Invoice.installment_number > 12
        )
    )
    assert len(rows.scalars().all()) == 2

    await db_session.refresh(ap)
    assert ap.is_final_cycle is True

    checklist = (await db_session.execute(
        select(DeedChecklist).where(DeedChecklist.client_lot_id == cl.id)
    )).scalar_one_or_none()
    assert checklist is not None, "final cycle must open the escrituração checklist"
    assert len(checklist.items) > 0


@pytest.mark.asyncio
async def test_approve_rejects_contract_already_fully_generated(
    client: AsyncClient, db_session: AsyncSession, test_company: Company, company_admin: Profile
):
    """Nothing left to generate is a 409, not a silent no-op approval."""
    _, cl = await _make_contract(db_session, test_company, total_installments=12)
    await _add_invoices(
        db_session, test_company, cl,
        first_number=1, count=12, first_due=date.today() - timedelta(days=300), settled=12,
    )
    ap = CycleApproval(
        id=uuid.uuid4(), company_id=test_company.id, client_lot_id=cl.id,
        cycle_number=2, status=CycleApprovalStatus.PENDING,
        previous_installment_value=Decimal("1000.00"),
    )
    db_session.add(ap)
    await db_session.flush()

    resp = await client.post(
        f"/api/v1/admin/cycle-approvals/{ap.id}/approve",
        json={"new_installment_value": "1050.00"},
        headers=auth_headers(company_admin),
    )
    assert resp.status_code == 409, resp.text


# ---------------------------------------------------------------------------
# Numbering, counters and manual opening
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_installment_numbering_survives_cancellations(
    client: AsyncClient, db_session: AsyncSession, test_company: Company, company_admin: Profile
):
    """Numbering follows max(), so a cancelled invoice cannot free its number."""
    _, cl = await _make_contract(db_session, test_company, total_installments=24)
    made = await _add_invoices(
        db_session, test_company, cl,
        first_number=1, count=12, first_due=date.today() - timedelta(days=300), settled=12,
    )
    made[3].status = InvoiceStatus.CANCELLED
    await db_session.flush()

    ap = CycleApproval(
        id=uuid.uuid4(), company_id=test_company.id, client_lot_id=cl.id,
        cycle_number=2, status=CycleApprovalStatus.PENDING,
        previous_installment_value=Decimal("1000.00"),
    )
    db_session.add(ap)
    await db_session.flush()

    resp = await client.post(
        f"/api/v1/admin/cycle-approvals/{ap.id}/force-approve",
        json={
            "new_installment_value": "1050.00",
            "justification": "Parcela 4 cancelada por acordo; ciclo liberado manualmente.",
        },
        headers=auth_headers(company_admin),
    )
    assert resp.status_code == 200, resp.text

    rows = await db_session.execute(
        select(Invoice.installment_number).where(Invoice.client_lot_id == cl.id)
    )
    numbers = [r[0] for r in rows.all()]
    assert len(numbers) == len(set(numbers)), f"duplicate installment_number: {numbers}"
    assert max(numbers) == 24


@pytest.mark.asyncio
async def test_duplicate_cycle_approval_is_rejected(
    db_session: AsyncSession, test_company: Company
):
    """The (client_lot_id, cycle_number) pair is unique at the database level."""
    from sqlalchemy.exc import IntegrityError

    _, cl = await _make_contract(db_session, test_company, total_installments=24)
    for _ in range(2):
        db_session.add(
            CycleApproval(
                id=uuid.uuid4(), company_id=test_company.id, client_lot_id=cl.id,
                cycle_number=2, status=CycleApprovalStatus.PENDING,
                previous_installment_value=Decimal("1000.00"),
            )
        )
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_pending_count_reports_final_and_blocked(
    client: AsyncClient, db_session: AsyncSession, test_company: Company, company_admin: Profile
):
    """The badge counters come from a cheap query, not the enriched list."""
    _, cl_a = await _make_contract(db_session, test_company, total_installments=24)
    _, cl_b = await _make_contract(db_session, test_company, total_installments=14)
    db_session.add_all([
        CycleApproval(
            id=uuid.uuid4(), company_id=test_company.id, client_lot_id=cl_a.id,
            cycle_number=2, status=CycleApprovalStatus.PENDING,
            previous_installment_value=Decimal("1000.00"), unpaid_count=3,
        ),
        CycleApproval(
            id=uuid.uuid4(), company_id=test_company.id, client_lot_id=cl_b.id,
            cycle_number=2, status=CycleApprovalStatus.PENDING,
            previous_installment_value=Decimal("1000.00"), is_final_cycle=True,
        ),
    ])
    await db_session.flush()

    resp = await client.get(
        "/api/v1/admin/cycle-approvals/pending-count",
        headers=auth_headers(company_admin),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["pending"] == 2
    assert body["final_cycle"] == 1
    assert body["blocked_by_unpaid"] == 1


@pytest.mark.asyncio
async def test_request_opens_renewal_ahead_of_schedule(
    client: AsyncClient, db_session: AsyncSession, test_company: Company, company_admin: Profile
):
    """An admin can open the renewal before the scheduled trigger raises it."""
    _, cl = await _make_contract(db_session, test_company, total_installments=24)
    await _add_invoices(
        db_session, test_company, cl,
        first_number=1, count=12, first_due=date.today() + timedelta(days=200), settled=0,
    )

    resp = await client.post(
        "/api/v1/admin/cycle-approvals/request",
        json={"client_lot_id": str(cl.id)},
        headers=auth_headers(company_admin),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["cycle_number"] == 2

    # Opening it twice is a conflict, not a duplicate row.
    again = await client.post(
        "/api/v1/admin/cycle-approvals/request",
        json={"client_lot_id": str(cl.id)},
        headers=auth_headers(company_admin),
    )
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_list_filters_by_client(
    client: AsyncClient, db_session: AsyncSession, test_company: Company, company_admin: Profile
):
    """?client_id= used to be ignored, returning the whole company."""
    client_a, cl_a = await _make_contract(db_session, test_company, total_installments=24)
    _, cl_b = await _make_contract(db_session, test_company, total_installments=24)
    db_session.add_all([
        CycleApproval(
            id=uuid.uuid4(), company_id=test_company.id, client_lot_id=cl_a.id,
            cycle_number=2, status=CycleApprovalStatus.PENDING,
            previous_installment_value=Decimal("1000.00"),
        ),
        CycleApproval(
            id=uuid.uuid4(), company_id=test_company.id, client_lot_id=cl_b.id,
            cycle_number=2, status=CycleApprovalStatus.PENDING,
            previous_installment_value=Decimal("1000.00"),
        ),
    ])
    await db_session.flush()

    resp = await client.get(
        f"/api/v1/admin/cycle-approvals?client_id={client_a.id}",
        headers=auth_headers(company_admin),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["client_lot_id"] == str(cl_a.id)


@pytest.mark.asyncio
async def test_retired_generate_next_batch_returns_410(
    client: AsyncClient, db_session: AsyncSession, test_company: Company, company_admin: Profile
):
    """The old bypass must not silently advance the cycle any more."""
    _, cl = await _make_contract(db_session, test_company, total_installments=24)
    before = cl.current_cycle

    resp = await client.post(
        f"/api/v1/admin/lots/client-lots/{cl.id}/generate-next-batch?adjustment_rate=0.05",
        headers=auth_headers(company_admin),
    )
    assert resp.status_code == 410, resp.text

    await db_session.refresh(cl)
    assert cl.current_cycle == before
