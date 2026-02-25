
"""Add sicredi_credentials table for Sicredi Cobrança API integration.

Revision ID: 002_sicredi_creds
Revises: 001_initial_tables
Create Date: 2025-02-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "002_sicredi_creds"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sicredi_credentials",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),

        # Sicredi API credentials (CONFIDENTIAL)
        sa.Column("x_api_key", sa.String(100), nullable=False),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("password", sa.String(255), nullable=False),

        # Cooperativa / Posto / Beneficiário
        sa.Column("cooperativa", sa.String(10), nullable=False),
        sa.Column("posto", sa.String(10), nullable=False),
        sa.Column("codigo_beneficiario", sa.String(20), nullable=False),

        # Environment
        sa.Column("environment", sa.String(20), nullable=False, server_default="production"),

        # Cached OAuth2 tokens (CRITICAL)
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=True),

        # Webhook
        sa.Column("webhook_contract_id", sa.String(100), nullable=True),

        # Active flag
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Performance index for multi-tenant queries
    op.create_index("idx_sicredi_creds_company_active", "sicredi_credentials", ["company_id", "is_active"])


def downgrade() -> None:
    op.drop_index("idx_sicredi_creds_company_active", table_name="sicredi_credentials")
    op.drop_table("sicredi_credentials")
