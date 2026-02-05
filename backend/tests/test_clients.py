"""Tests for admin client management."""

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch

from app.models.user import Profile
from tests.conftest import auth_headers


@pytest.mark.asyncio
@patch("app.api.v1.admin.clients.create_customer", new_callable=AsyncMock, return_value="cus_test123")
async def test_create_client(mock_asaas, client: AsyncClient, company_admin: Profile):
    """Admin can create a client."""
    resp = await client.post(
        "/api/v1/admin/clients/",
        headers=auth_headers(company_admin),
        json={
            "email": "newclient@test.com",
            "full_name": "New Client",
            "cpf_cnpj": "55555555555",
            "phone": "11666660000",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["full_name"] == "New Client"
    assert data["asaas_customer_id"] == "cus_test123"


@pytest.mark.asyncio
@patch("app.api.v1.admin.clients.create_customer", new_callable=AsyncMock, return_value="cus_x")
async def test_get_client(mock_asaas, client: AsyncClient, company_admin: Profile):
    """Admin can retrieve a specific client."""
    # Create first
    create_resp = await client.post(
        "/api/v1/admin/clients/",
        headers=auth_headers(company_admin),
        json={
            "email": "get@test.com",
            "full_name": "Get Me",
            "cpf_cnpj": "66666666666",
            "phone": "11555550000",
        },
    )
    client_id = create_resp.json()["id"]

    resp = await client.get(
        f"/api/v1/admin/clients/{client_id}",
        headers=auth_headers(company_admin),
    )
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Get Me"


@pytest.mark.asyncio
@patch("app.api.v1.admin.clients.create_customer", new_callable=AsyncMock, return_value="cus_y")
async def test_update_client(mock_asaas, client: AsyncClient, company_admin: Profile):
    """Admin can update client data."""
    create_resp = await client.post(
        "/api/v1/admin/clients/",
        headers=auth_headers(company_admin),
        json={
            "email": "upd@test.com",
            "full_name": "Before Update",
            "cpf_cnpj": "77777777777",
            "phone": "11444440000",
        },
    )
    client_id = create_resp.json()["id"]

    resp = await client.put(
        f"/api/v1/admin/clients/{client_id}",
        headers=auth_headers(company_admin),
        json={"full_name": "After Update"},
    )
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "After Update"


@pytest.mark.asyncio
@patch("app.api.v1.admin.clients.create_customer", new_callable=AsyncMock, return_value="cus_z")
async def test_deactivate_client(mock_asaas, client: AsyncClient, company_admin: Profile):
    """Admin can soft-delete (deactivate) a client."""
    create_resp = await client.post(
        "/api/v1/admin/clients/",
        headers=auth_headers(company_admin),
        json={
            "email": "del@test.com",
            "full_name": "To Delete",
            "cpf_cnpj": "12312312312",
            "phone": "11333330000",
        },
    )
    client_id = create_resp.json()["id"]

    resp = await client.delete(
        f"/api/v1/admin/clients/{client_id}",
        headers=auth_headers(company_admin),
    )
    assert resp.status_code == 204

    # Verify it's inactive
    get_resp = await client.get(
        f"/api/v1/admin/clients/{client_id}",
        headers=auth_headers(company_admin),
    )
    assert get_resp.json()["status"] == "inactive"
