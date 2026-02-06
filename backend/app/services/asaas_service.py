from typing import Optional

"""Asaas payment gateway integration service."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import httpx

from app.core.config import settings
from app.utils.exceptions import AsaasIntegrationError
from app.utils.logging import get_logger

logger = get_logger(__name__)

ASAAS_HEADERS = {
    "Content-Type": "application/json",
    "access_token": "",  # set at runtime
}


def _headers() -> dict:
    """Build Asaas request headers."""
    return {
        "Content-Type": "application/json",
        "access_token": settings.ASAAS_API_KEY,
    }


async def create_customer(
    name: str,
    cpf_cnpj: str,
    email: str,
    phone: Optional[str] = None,
) -> str:
    """Create a customer in Asaas and return the asaas_customer_id."""
    payload = {
        "name": name,
        "cpfCnpj": cpf_cnpj,
        "email": email,
    }
    if phone:
        payload["mobilePhone"] = phone

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{settings.ASAAS_BASE_URL}/customers",
            json=payload,
            headers=_headers(),
        )

    if resp.status_code not in (200, 201):
        logger.error("asaas_create_customer_failed", status=resp.status_code, body=resp.text)
        raise AsaasIntegrationError(f"Failed to create Asaas customer: {resp.text}")

    data = resp.json()
    logger.info("asaas_customer_created", asaas_id=data["id"])
    return data["id"]


async def create_boleto(
    asaas_customer_id: str,
    value: Decimal,
    due_date: date,
    description: str = "",
    installment_number: int = 1,
) -> dict:
    """Generate a boleto (bank slip) in Asaas.

    Returns dict with keys: asaas_payment_id, barcode, payment_url.
    """
    payload = {
        "customer": asaas_customer_id,
        "billingType": "BOLETO",
        "value": float(value),
        "dueDate": due_date.isoformat(),
        "description": description or f"Parcela {installment_number}",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{settings.ASAAS_BASE_URL}/payments",
            json=payload,
            headers=_headers(),
        )

    if resp.status_code not in (200, 201):
        logger.error("asaas_create_boleto_failed", status=resp.status_code, body=resp.text)
        raise AsaasIntegrationError(f"Failed to create boleto: {resp.text}")

    data = resp.json()
    logger.info("asaas_boleto_created", payment_id=data["id"])

    return {
        "asaas_payment_id": data["id"],
        "barcode": data.get("bankSlipUrl", ""),
        "payment_url": data.get("invoiceUrl", ""),
    }


async def get_payment(asaas_payment_id: str) -> dict:
    """Retrieve a single payment from Asaas."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{settings.ASAAS_BASE_URL}/payments/{asaas_payment_id}",
            headers=_headers(),
        )

    if resp.status_code != 200:
        raise AsaasIntegrationError(f"Failed to get payment: {resp.text}")

    return resp.json()


async def list_overdue_payments(offset: int = 0, limit: int = 100) -> list[dict]:
    """List overdue payments from Asaas."""
    params = {"status": "OVERDUE", "offset": offset, "limit": limit}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{settings.ASAAS_BASE_URL}/payments",
            params=params,
            headers=_headers(),
        )

    if resp.status_code != 200:
        raise AsaasIntegrationError(f"Failed to list overdue payments: {resp.text}")

    return resp.json().get("data", [])
