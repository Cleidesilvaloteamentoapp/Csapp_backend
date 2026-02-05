"""Tests for company management endpoints (super_admin)."""

import pytest
from httpx import AsyncClient

from app.models.company import Company
from app.models.user import Profile
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_create_company(client: AsyncClient, super_admin: Profile):
    """Super admin can create a new company."""
    resp = await client.post(
        "/api/v1/companies/",
        headers=auth_headers(super_admin),
        json={"name": "Created Co", "slug": "created-co"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Created Co"
    assert data["slug"] == "created-co"
    assert data["status"] == "active"


@pytest.mark.asyncio
async def test_create_company_duplicate_slug(
    client: AsyncClient, super_admin: Profile, test_company: Company
):
    """Creating a company with an existing slug should fail."""
    resp = await client.post(
        "/api/v1/companies/",
        headers=auth_headers(super_admin),
        json={"name": "Dup", "slug": "test-company"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_company(
    client: AsyncClient, super_admin: Profile, test_company: Company
):
    """Super admin can retrieve a specific company."""
    resp = await client.get(
        f"/api/v1/companies/{test_company.id}",
        headers=auth_headers(super_admin),
    )
    assert resp.status_code == 200
    assert resp.json()["slug"] == "test-company"


@pytest.mark.asyncio
async def test_update_company(
    client: AsyncClient, super_admin: Profile, test_company: Company
):
    """Super admin can update a company."""
    resp = await client.put(
        f"/api/v1/companies/{test_company.id}",
        headers=auth_headers(super_admin),
        json={"name": "Updated Name"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_suspend_company(
    client: AsyncClient, super_admin: Profile, test_company: Company
):
    """Super admin can suspend a company."""
    resp = await client.patch(
        f"/api/v1/companies/{test_company.id}/status",
        headers=auth_headers(super_admin),
        json={"status": "suspended"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "suspended"
