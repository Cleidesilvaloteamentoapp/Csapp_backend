"""Turn an approved cycle into actual boletos.

Approving a cycle used to create Invoice rows and stop there, leaving an admin
to go and issue the 12 boletos by hand on another screen -- which is where the
renewal quietly stalled. This service closes that gap by enqueueing the same
batch job the Boletos screen uses, bound to the invoices just generated.
"""

from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.batch_operation import BatchOperation
from app.models.client import Client
from app.models.client_lot import ClientLot
from app.models.invoice import Invoice
from app.utils.logging import get_logger

logger = get_logger(__name__)


def build_pagador(client: Client) -> Optional[dict]:
    """Payer block for Sicredi, from the client's own registration.

    Returns None when the address is too incomplete to register a boleto, so the
    caller can tell the admin to complete the cadastro instead of firing a batch
    that the bank will reject twelve times.
    """
    addr = client.address or {}
    documento = "".join(ch for ch in (client.cpf_cnpj or "") if ch.isdigit())
    cep = "".join(ch for ch in str(addr.get("zip") or "") if ch.isdigit())
    street = addr.get("street") or ""
    endereco = f"{street}, {addr.get('number') or 'S/N'}" if street else ""
    cidade = addr.get("city") or ""
    uf = addr.get("state") or ""

    if not (documento and client.full_name and endereco and cidade and uf and cep):
        return None

    return {
        "tipo_pessoa": "PESSOA_FISICA" if len(documento) <= 11 else "PESSOA_JURIDICA",
        "documento": documento,
        "nome": client.full_name,
        "endereco": endereco,
        "cidade": cidade,
        "uf": uf,
        "cep": cep,
    }


async def enqueue_cycle_boletos(
    db: AsyncSession,
    *,
    company_id: UUID,
    client_lot: ClientLot,
    invoices: list[Invoice],
    created_by: UUID,
) -> tuple[Optional[BatchOperation], Optional[str]]:
    """Queue boleto creation for the invoices a cycle approval just generated.

    Returns (batch, reason_not_queued). A None batch is not a failure of the
    approval -- the invoices exist either way; it means the boletos have to be
    issued manually, and the reason says why.
    """
    from sqlalchemy import select

    from app.services.sicredi_service import get_credential

    if not invoices:
        return None, "Nenhuma parcela nova para gerar boleto."

    cred = await get_credential(db, company_id)
    if not cred:
        return None, (
            "Credenciais Sicredi não cadastradas: as parcelas foram criadas, "
            "mas os boletos precisam ser emitidos após configurar a integração."
        )

    client = (await db.execute(
        select(Client).where(Client.id == client_lot.client_id)
    )).scalar_one_or_none()
    if not client:
        return None, "Cliente não encontrado."

    pagador = build_pagador(client)
    if not pagador:
        return None, (
            "Endereço do cliente incompleto (rua, cidade, UF e CEP são obrigatórios "
            "para registrar boleto). As parcelas foram criadas; complete o cadastro "
            "e emita os boletos."
        )

    ordered = sorted(invoices, key=lambda inv: inv.due_date)
    valor = ordered[0].amount

    input_data = {
        "client_id": str(client.id),
        "client_lot_id": str(client_lot.id),
        "created_by": str(created_by),
        "pagador": pagador,
        "valor": str(Decimal(valor)),
        "frequency": "MENSAL",
        "duration_months": len(ordered),
        "data_primeiro_vencimento": ordered[0].due_date.isoformat(),
        "tipo_cobranca": "HIBRIDO",
        "especie_documento": "DUPLICATA_MERCANTIL_INDICACAO",
    }

    batch = BatchOperation(
        company_id=company_id,
        type="BATCH_CREATE",
        status="PENDING",
        client_id=client.id,
        frequency="MENSAL",
        duration_months=len(ordered),
        total_items=len(ordered),
        input_data=input_data,
        results=[],
        created_by=created_by,
    )
    db.add(batch)
    await db.flush()

    logger.info(
        "cycle_boletos_enqueued",
        batch_id=str(batch.id),
        client_lot_id=str(client_lot.id),
        installments=len(ordered),
    )
    return batch, None


def dispatch(batch: Optional[BatchOperation], company_id: UUID) -> None:
    """Hand the batch to Celery. Called after the surrounding commit.

    Enqueueing before the commit would race the worker against a transaction
    that has not written the BatchOperation yet.
    """
    if batch is None:
        return
    from app.tasks.batch_tasks import process_batch_creation

    process_batch_creation.delay(str(batch.id), str(company_id))
