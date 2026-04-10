"""Add STAFF role, is_active to profiles, and staff_permissions table.

Revision ID: 011_staff_permissions
Revises: 010_property_types
Create Date: 2026-04-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "011_staff_permissions"
down_revision = "010_property_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add STAFF to user_role enum
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'STAFF'")

    # 2. Add is_active to profiles
    op.add_column(
        "profiles",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="Whether the user account is active (STAFF accounts can be disabled)",
        ),
    )

    # 3. Create staff_permissions table
    op.create_table(
        "staff_permissions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column(
            "company_id",
            UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Clients
        sa.Column("view_clients", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("manage_clients", sa.Boolean(), nullable=False, server_default="false"),
        # Lots
        sa.Column("view_lots", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("manage_lots", sa.Boolean(), nullable=False, server_default="false"),
        # Financial / Boletos
        sa.Column("view_financial", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("manage_financial", sa.Boolean(), nullable=False, server_default="false"),
        # Renegotiations
        sa.Column("view_renegotiations", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("manage_renegotiations", sa.Boolean(), nullable=False, server_default="false"),
        # Rescissions
        sa.Column("view_rescissions", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("manage_rescissions", sa.Boolean(), nullable=False, server_default="false"),
        # Reports
        sa.Column("view_reports", sa.Boolean(), nullable=False, server_default="false"),
        # Service Requests
        sa.Column("view_service_requests", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("manage_service_requests", sa.Boolean(), nullable=False, server_default="false"),
        # Documents
        sa.Column("view_documents", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("manage_documents", sa.Boolean(), nullable=False, server_default="false"),
        # Sicredi
        sa.Column("view_sicredi", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("manage_sicredi", sa.Boolean(), nullable=False, server_default="false"),
        # WhatsApp
        sa.Column("view_whatsapp", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("manage_whatsapp", sa.Boolean(), nullable=False, server_default="false"),
        # Financial Settings
        sa.Column("view_financial_settings", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("manage_financial_settings", sa.Boolean(), nullable=False, server_default="false"),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_index("idx_staff_permissions_company", "staff_permissions", ["company_id"])
    op.create_index("idx_staff_permissions_profile", "staff_permissions", ["profile_id"])


def downgrade() -> None:
    op.drop_index("idx_staff_permissions_profile", table_name="staff_permissions")
    op.drop_index("idx_staff_permissions_company", table_name="staff_permissions")
    op.drop_table("staff_permissions")
    op.drop_column("profiles", "is_active")
    # NOTE: PostgreSQL does not support removing enum values; STAFF enum value stays
