"""Add BAIXA_EXTERNA to the writeoff_type enum.

``WriteoffType.BAIXA_EXTERNA`` was added to the model to mark boletos that were
written off directly at Sicredi (situação BAIXADO / BAIXADO POR SOLICITACAO),
but the Postgres type was still the two-value enum created in
006_client_adjustments. Every reconciliation that found such a boleto failed the
flush with ``invalid input value for enum writeoff_type: "BAIXA_EXTERNA"``,
poisoning the session and turning the whole sync into a 500.

Revision ID: 017_writeoff_type_baixa_externa
Revises: 016_sicredi_event_webhook_id
Create Date: 2026-09-09
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "017_writeoff_type_baixa_externa"
down_revision = "016_sicredi_event_webhook_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE needs its own transaction on PostgreSQL < 12, and
    # on every version the new label cannot be *used* in the transaction that
    # adds it. autocommit_block keeps both rules satisfied.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE writeoff_type ADD VALUE IF NOT EXISTS 'BAIXA_EXTERNA'")


def downgrade() -> None:
    # PostgreSQL cannot drop a value from an enum type. Removing it would mean
    # rebuilding writeoff_type and rewriting boletos.writeoff_type, which would
    # destroy the rows this migration exists to make writable.
    pass
