"""SUPER_ADMIN is the platform role; COMPANY_ADMIN runs one company.

Before this split the two were interchangeable everywhere except a handful of
endpoints, and *nothing* could create a COMPANY_ADMIN -- signup minted
SUPER_ADMIN, so every tenant's administrator held the platform role.
"""

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.cycle_approval import CycleApproval
from app.models.enums import CompanyStatus, CycleApprovalStatus, UserRole
from app.models.user import Profile
from tests.conftest import auth_headers
from tests.test_cycle_approvals import _make_contract


ADMIN_PAYLOAD = {
    "full_name": "Admin da Revenda",
    "email": "revenda@nova.com",
    "cpf_cnpj": "98765432100",
    "phone": "11977776666",
    "password": "SenhaForte1!",
}


@pytest.mark.asyncio
async def test_signup_creates_company_admin_not_platform_admin(db_session: AsyncSession):
    """Signing up must not hand out the cross-company role.

    Calls the service rather than the route: the signup endpoint is rate
    limited to 3/minute, which the suite exhausts before reaching this.
    """
    from app.schemas.auth import SignupRequest
    from app.services import auth_service

    email = f"dono{uuid.uuid4().hex[:6]}@nova.com"
    await auth_service.signup(
        SignupRequest(
            company_name="Nova Empresa",
            company_slug=f"nova-{uuid.uuid4().hex[:6]}",
            full_name="Dono",
            email=email,
            cpf_cnpj=uuid.uuid4().hex[:11],
            phone="11966665555",
            password="SenhaForte1!",
        ),
        db_session,
    )

    profile = (await db_session.execute(
        select(Profile).where(Profile.email == email)
    )).scalar_one()
    assert profile.role == UserRole.COMPANY_ADMIN


@pytest.mark.asyncio
async def test_super_admin_creates_company_and_its_first_admin(
    client: AsyncClient, db_session: AsyncSession, super_admin: Profile
):
    """The reseller flow: a company plus someone who can actually log into it."""
    slug = f"revenda-{uuid.uuid4().hex[:6]}"
    created = await client.post(
        "/api/v1/companies",
        json={"name": "Empresa Revendida", "slug": slug},
        headers=auth_headers(super_admin),
    )
    assert created.status_code == 201, created.text
    company_id = created.json()["id"]

    admin = await client.post(
        f"/api/v1/companies/{company_id}/admins",
        json=ADMIN_PAYLOAD,
        headers=auth_headers(super_admin),
    )
    assert admin.status_code == 201, admin.text
    assert admin.json()["role"] == "COMPANY_ADMIN"
    assert admin.json()["company_id"] == company_id

    listed = await client.get(
        f"/api/v1/companies/{company_id}/admins", headers=auth_headers(super_admin)
    )
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) == 1


@pytest.mark.asyncio
async def test_company_admin_cannot_create_companies_or_admins(
    client: AsyncClient, db_session: AsyncSession, company_admin: Profile, test_company: Company
):
    """Company creation is the platform's job, not a tenant's."""
    resp = await client.post(
        "/api/v1/companies",
        json={"name": "Não Deveria", "slug": f"nope-{uuid.uuid4().hex[:6]}"},
        headers=auth_headers(company_admin),
    )
    assert resp.status_code == 403, resp.text

    resp2 = await client.post(
        f"/api/v1/companies/{test_company.id}/admins",
        json=ADMIN_PAYLOAD,
        headers=auth_headers(company_admin),
    )
    assert resp2.status_code == 403, resp2.text


@pytest.mark.asyncio
async def test_super_admin_reads_another_company_via_explicit_scope(
    client: AsyncClient,
    db_session: AsyncSession,
    test_company: Company,
    test_company_b: Company,
    super_admin: Profile,
):
    """?company_id= is the deliberate, logged cross-company override."""
    _, cl = await _make_contract(db_session, test_company_b, total_installments=24)
    db_session.add(
        CycleApproval(
            id=uuid.uuid4(), company_id=test_company_b.id, client_lot_id=cl.id,
            cycle_number=2, status=CycleApprovalStatus.PENDING,
            previous_installment_value=Decimal("1000.00"),
        )
    )
    await db_session.flush()

    # super_admin belongs to test_company, so its own queue is empty...
    own = await client.get(
        "/api/v1/admin/dashboard/action-queue", headers=auth_headers(super_admin)
    )
    assert own.status_code == 200, own.text
    assert next(i for i in own.json()["items"] if i["key"] == "cycle_approvals")["count"] == 0

    # ...but it may look at company B explicitly.
    other = await client.get(
        f"/api/v1/admin/dashboard/action-queue?company_id={test_company_b.id}",
        headers=auth_headers(super_admin),
    )
    assert other.status_code == 200, other.text
    assert next(i for i in other.json()["items"] if i["key"] == "cycle_approvals")["count"] == 1


@pytest.mark.asyncio
async def test_company_admin_cannot_use_the_scope_override(
    client: AsyncClient,
    db_session: AsyncSession,
    test_company_b: Company,
    company_admin: Profile,
):
    """A tenant admin passing ?company_id= is refused, not silently ignored."""
    resp = await client.get(
        f"/api/v1/admin/dashboard/action-queue?company_id={test_company_b.id}",
        headers=auth_headers(company_admin),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_suspended_company_blocks_login(
    client: AsyncClient, db_session: AsyncSession, test_company: Company, company_admin: Profile
):
    """Suspending a company was settable but enforced nowhere."""
    ok = await client.post(
        "/api/v1/auth/login",
        json={"email": company_admin.email, "password": "TestPass123!"},
    )
    assert ok.status_code == 200, ok.text

    test_company.status = CompanyStatus.SUSPENDED
    await db_session.flush()

    blocked = await client.post(
        "/api/v1/auth/login",
        json={"email": company_admin.email, "password": "TestPass123!"},
    )
    assert blocked.status_code == 401, blocked.text
    assert "suspensa" in blocked.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_superadmins_endpoint_exists(
    client: AsyncClient, db_session: AsyncSession, super_admin: Profile
):
    """The staff screen has always called this; it used to 404 and render empty."""
    resp = await client.get(
        "/api/v1/admin/superadmins", headers=auth_headers(super_admin)
    )
    assert resp.status_code == 200, resp.text
    emails = [r["email"] for r in resp.json()]
    assert super_admin.email in emails
