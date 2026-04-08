"""Add paid_installments field to client_lots for legacy client tracking.

Revision ID: 009_add_paid_installments
Revises: 008_whatsapp_credentials
Create Date: 2026-04-08
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "009_add_paid_installments"
down_revision = "008_whatsapp_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "client_lots",
        sa.Column(
            "paid_installments",
            sa.Integer(),
            nullable=True,
            server_default="0",
            comment="Manual count of paid installments for legacy clients (before system tracking)",
        ),
    )


def downgrade() -> None:
    op.drop_column("client_lots", "paid_installments")
