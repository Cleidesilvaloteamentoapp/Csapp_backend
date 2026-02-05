"""Tests for the Asaas webhook endpoint."""

import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client_lot import ClientLot
from app.models.company import Company
from app.models.client import Client
from app.models.enums import ClientLotStatus, ClientStatus, InvoiceStatus
from app.models.invoice import Invoice
from app.models.user import Profile


@pytest.mark.asyncio
async def test_webhook_payment_received(
    client: AsyncClient,
    db_session: AsyncSession,
    test_company: Company,
    company_admin: Profile,
):
    """PAYMENT_RECEIVED should mark invoice as paid."""
    # Setup: create client, client_lot, invoice
    cl = Client(
        company_id=test_company.id,
        email="wh@test.com",
        full_name="WH Client",
        cpf_cnpj="10101010101",
        phone="11222220000",
        status=ClientStatus.ACTIVE,
    )
    db_session.add(cl)
    await db_session.flush()

    cl_lot = ClientLot(
        company_id=test_company.id,
        client_id=cl.id,
        lot_id=uuid.uuid4(),  # Dummy – not validated in webhook
        purchase_date=date.today(),
        total_value=10000,
        status=ClientLotStatus.ACTIVE,
    )
    db_session.add(cl_lot)
    await db_session.flush()

    inv = Invoice(
        company_id=test_company.id,
        client_lot_id=cl_lot.id,
        due_date=date.today(),
        amount=1000,
        installment_number=1,
        status=InvoiceStatus.PENDING,
        asaas_payment_id="pay_webhook_test",
    )
    db_session.add(inv)
    await db_session.flush()

    # Send webhook
    resp = await client.post(
        "/api/v1/webhooks/asaas",
        json={
            "event": "PAYMENT_RECEIVED",
            "payment": {"id": "pay_webhook_test"},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["new_status"] == "paid"


@pytest.mark.asyncio
async def test_webhook_unknown_payment(client: AsyncClient):
    """Webhook with unknown payment ID should return ignored."""
    resp = await client.post(
        "/api/v1/webhooks/asaas",
        json={
            "event": "PAYMENT_RECEIVED",
            "payment": {"id": "pay_nonexistent"},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
