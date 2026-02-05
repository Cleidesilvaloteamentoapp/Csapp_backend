"""Tests for authentication endpoints."""

import pytest
from httpx import AsyncClient

from app.models.user import Profile
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_signup_success(client: AsyncClient):
    """Signup should create company + profile and return tokens."""
    resp = await client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": "New Co",
            "company_slug": "new-co",
            "full_name": "John Doe",
            "email": "john@newco.com",
            "password": "Str0ngPass!",
            "cpf_cnpj": "99999999999",
            "phone": "11888880000",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_signup_duplicate_slug(client: AsyncClient):
    """Signup with an existing slug should return 409."""
    payload = {
        "company_name": "Dup Co",
        "company_slug": "dup-co",
        "full_name": "Jane Doe",
        "email": "jane@dup.com",
        "password": "Str0ngPass!",
        "cpf_cnpj": "88888888888",
        "phone": "11888881111",
    }
    await client.post("/api/v1/auth/signup", json=payload)
    resp = await client.post(
        "/api/v1/auth/signup",
        json={**payload, "email": "other@dup.com", "cpf_cnpj": "77777777777"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, super_admin: Profile):
    """Login with correct credentials should return tokens."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "superadmin@test.com", "password": "TestPass123!"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, super_admin: Profile):
    """Login with wrong password should return 401."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "superadmin@test.com", "password": "WrongPassword"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_authenticated(client: AsyncClient, super_admin: Profile):
    """GET /me should return profile data."""
    resp = await client.get("/api/v1/auth/me", headers=auth_headers(super_admin))
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "superadmin@test.com"
    assert data["role"] == "super_admin"


@pytest.mark.asyncio
async def test_me_unauthenticated(client: AsyncClient):
    """GET /me without token should return 401."""
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient, super_admin: Profile):
    """Refresh should return a new token pair."""
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "superadmin@test.com", "password": "TestPass123!"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()
