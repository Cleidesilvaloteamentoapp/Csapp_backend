
"""Add company_financial_settings table for global financial defaults per company.

Revision ID: 007_company_financial_settings
Revises: 006_client_adjustments
Create Date: 2026-03-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "007_company_financial_settings"
down_revision = "006_client_adjustments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_financial_settings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("penalty_rate", sa.Numeric(6, 4), nullable=False, server_default="0.02"),
        sa.Column("daily_interest_rate", sa.Numeric(8, 6), nullable=False, server_default="0.000330"),
        sa.Column(
            "adjustment_index",
            sa.Enum("IPCA", "IGPM", "CUB", "INPC", name="adjustment_index", create_type=False),
            nullable=False,
            server_default="IPCA",
        ),
        sa.Column(
            "adjustment_frequency",
            sa.Enum("MONTHLY", "QUARTERLY", "SEMIANNUAL", "ANNUAL", name="adjustment_frequency", create_type=False),
            nullable=False,
            server_default="ANNUAL",
        ),
        sa.Column("adjustment_custom_rate", sa.Numeric(6, 4), nullable=False, server_default="0.05"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("company_id", name="uq_company_financial_settings_company"),
    )


def downgrade() -> None:
    op.drop_table("company_financial_settings")
