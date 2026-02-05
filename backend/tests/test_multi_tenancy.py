"""Tests for multi-tenant isolation."""

import pytest
from httpx import AsyncClient

from app.models.company import Company
from app.models.user import Profile
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_company_admin_cannot_access_other_company(
    client: AsyncClient,
    company_admin: Profile,
    test_company_b: Company,
):
    """company_admin should NOT see data from another company."""
    # Try to access other company's details (super_admin endpoint)
    resp = await client.get(
        f"/api/v1/companies/{test_company_b.id}",
        headers=auth_headers(company_admin),
    )
    # company_admin is not super_admin, so should get 403
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_super_admin_can_see_all_companies(
    client: AsyncClient,
    super_admin: Profile,
    test_company: Company,
    test_company_b: Company,
):
    """super_admin should see all companies."""
    resp = await client.get("/api/v1/companies/", headers=auth_headers(super_admin))
    assert resp.status_code == 200
    data = resp.json()
    slugs = [c["slug"] for c in data["items"]]
    assert "test-company" in slugs
    assert "other-company" in slugs


@pytest.mark.asyncio
async def test_client_cannot_access_admin_endpoints(
    client: AsyncClient,
    client_user: Profile,
):
    """Client role should not access admin endpoints."""
    resp = await client.get(
        "/api/v1/admin/clients/",
        headers=auth_headers(client_user),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_clients_isolated_by_company(
    client: AsyncClient,
    company_admin: Profile,
    company_admin_b: Profile,
):
    """Each admin should only see their own company's clients."""
    # Admin A creates a client
    resp_a = await client.post(
        "/api/v1/admin/clients/",
        headers=auth_headers(company_admin),
        json={
            "email": "clientA@test.com",
            "full_name": "Client A",
            "cpf_cnpj": "44444444444",
            "phone": "11777770000",
        },
    )
    assert resp_a.status_code == 201

    # Admin B lists clients – should NOT see Client A
    resp_b = await client.get(
        "/api/v1/admin/clients/",
        headers=auth_headers(company_admin_b),
    )
    assert resp_b.status_code == 200
    names = [c["full_name"] for c in resp_b.json()["items"]]
    assert "Client A" not in names
