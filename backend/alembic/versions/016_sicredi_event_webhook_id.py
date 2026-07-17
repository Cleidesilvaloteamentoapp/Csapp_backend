"""Add webhook_event_id to sicredi_events for webhook idempotency.

Stores Sicredi's idEventoWebhook so redelivered webhook notifications can be
detected and skipped (recorded as WEBHOOK_DUPLICATE) instead of re-processing a
liquidation. Indexed but intentionally NOT unique — duplicate rows must remain
insertable so the redelivery stays visible in the audit trail.

Revision ID: 016_sicredi_event_webhook_id
Revises: 015_lot_balneario_matricula
Create Date: 2026-07-16
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "016_sicredi_event_webhook_id"
down_revision = "015_lot_balneario_matricula"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sicredi_events",
        sa.Column(
            "webhook_event_id",
            sa.String(100),
            nullable=True,
            comment="Sicredi idEventoWebhook (idempotency key for inbound webhooks)",
        ),
    )
    op.create_index(
        "ix_sicredi_events_webhook_event_id",
        "sicredi_events",
        ["webhook_event_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_sicredi_events_webhook_event_id", table_name="sicredi_events")
    op.drop_column("sicredi_events", "webhook_event_id")
