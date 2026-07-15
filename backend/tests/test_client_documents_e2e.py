"""End-to-end test for the client document attach → list flow (the goal).

Exercises the real ASGI app + Postgres: upload a document for a client, then
confirm GET /admin/clients/{id}/documents returns the structured document
(name, type, signed file_url) so it shows up on the client's ficha.
"""

import io
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.models.client import Client
from app.models.enums import ClientStatus
from app.models.user import Profile
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_upload_then_list_client_documents(
    client: AsyncClient, company_admin: Profile, db_session
):
    """A document uploaded for a client is returned by the ficha's list endpoint."""
    # Arrange: a client belonging to the admin's company.
    c = Client(
        id=uuid.uuid4(),
        company_id=company_admin.company_id,
        full_name="Fulano de Tal",
        email="fulano@test.com",
        cpf_cnpj="98765432100",
        phone="11987654321",
        status=ClientStatus.ACTIVE,
    )
    db_session.add(c)
    await db_session.flush()

    fake_path = "companies/x/clients/y/documents/abc.pdf"
    signed_url = "https://signed.example/abc.pdf?token=xyz"

    # Act 1: upload a PROPERTY document (MATRICULA → categoria IMOVEL).
    with patch(
        "app.api.v1.admin.clients.upload_file",
        new_callable=AsyncMock,
        return_value=fake_path,
    ), patch(
        "app.api.v1.admin.clients.get_public_url",
        return_value=signed_url,
    ):
        up = await client.post(
            f"/api/v1/admin/clients/{c.id}/documents",
            headers=auth_headers(company_admin),
            data={
                "document_type": "MATRICULA",
                "description": "Matrícula do imóvel",
                "tags": '["urgente"]',
                "visible_to_client": "true",
            },
            files={"file": ("matricula.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
        )
    assert up.status_code == 201, up.text
    created = up.json()
    assert created["file_name"] == "matricula.pdf"
    assert created["document_type"] == "MATRICULA"
    assert created["file_url"] == signed_url

    # Act 2: list documents like the client's ficha does.
    with patch("app.api.v1.admin.clients.get_public_url", return_value=signed_url):
        listed = await client.get(
            f"/api/v1/admin/clients/{c.id}/documents",
            headers=auth_headers(company_admin),
        )

    # Assert: the uploaded doc shows up as a STRUCTURED object (the bug was this
    # endpoint returning legacy JSONB string URLs → always empty).
    assert listed.status_code == 200, listed.text
    docs = listed.json()
    assert isinstance(docs, list) and len(docs) == 1, docs
    doc = docs[0]
    assert isinstance(doc, dict), f"expected structured object, got {type(doc)}: {doc}"
    assert doc["file_name"] == "matricula.pdf"
    assert doc["document_type"] == "MATRICULA"       # nome + tipo
    assert doc["file_url"] == signed_url             # botão visualizar/download
    assert doc["tags"] == ["urgente"]
    assert doc["visible_to_client"] is True
    assert doc["id"] == created["id"]
