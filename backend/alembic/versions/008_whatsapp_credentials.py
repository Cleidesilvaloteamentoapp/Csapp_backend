
"""Add whatsapp_credentials table for multi-provider WhatsApp integration.

Revision ID: 008_whatsapp_credentials
Revises: 007_company_financial_settings
Create Date: 2026-03-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "008_whatsapp_credentials"
down_revision = "007_company_financial_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum type
    whatsapp_provider_type = sa.Enum("UAZAPI", "META", name="whatsapp_provider_type")
    whatsapp_provider_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "whatsapp_credentials",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column(
            "provider",
            sa.Enum("UAZAPI", "META", name="whatsapp_provider_type", create_type=False),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        # UAZAPI fields
        sa.Column("uazapi_base_url", sa.String(500), nullable=True),
        sa.Column("uazapi_instance_token", sa.Text(), nullable=True),
        # Meta Cloud API fields
        sa.Column("meta_waba_id", sa.String(100), nullable=True),
        sa.Column("meta_phone_number_id", sa.String(100), nullable=True),
        sa.Column("meta_access_token", sa.Text(), nullable=True),
        # Connection status cache
        sa.Column("connection_status", sa.String(20), nullable=True, server_default="unknown"),
        sa.Column("last_status_check", sa.DateTime(timezone=True), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        # Constraints
        sa.UniqueConstraint("company_id", "provider", name="uq_whatsapp_company_provider"),
    )


def downgrade() -> None:
    op.drop_table("whatsapp_credentials")
    sa.Enum(name="whatsapp_provider_type").drop(op.get_bind(), checkfirst=True)
