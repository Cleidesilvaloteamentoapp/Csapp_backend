"""Manual adjustment index per contract + client profile photo.

Adds:
- client_lots.manual_index_value: per-contract manual index %% (e.g. IPCA do dia)
  overriding the economic_indices lookup at adjustment time.
- clients.photo_url: optional profile photo for the client (central do cliente).

Revision ID: 013_manual_index_and_client_photo
Revises: 012_document_tags_and_types
Create Date: 2026-06-09
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "013_manual_index_and_client_photo"
down_revision = "012_document_tags_and_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "client_lots",
        sa.Column(
            "manual_index_value",
            sa.Numeric(8, 4),
            nullable=True,
            comment="Manual index %% (e.g. IPCA do dia) overriding economic_indices lookup",
        ),
    )
    op.add_column(
        "clients",
        sa.Column(
            "photo_url",
            sa.String(length=500),
            nullable=True,
            comment="Optional profile photo storage path/URL",
        ),
    )


def downgrade() -> None:
    op.drop_column("clients", "photo_url")
    op.drop_column("client_lots", "manual_index_value")
