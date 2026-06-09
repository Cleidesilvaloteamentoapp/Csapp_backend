"""Add company_notification_settings table and new NotificationType enum values.

Revision ID: 014_notification_settings
Revises: 013_manual_index_and_client_photo
Create Date: 2026-06-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "014_notification_settings"
down_revision = "013_manual_index_and_client_photo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new values to the notification_type enum
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'BOLETO_CANCELADO'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'CLIENTE_CADASTRADO'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'CLIENTE_EXCLUIDO'")

    op.create_table(
        "company_notification_settings",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # Client toggles
        sa.Column("notify_client_new_boleto", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notify_client_due_reminder", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notify_client_overdue", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notify_client_service", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        # Admin toggles
        sa.Column("notify_admin_client_created", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notify_admin_client_deleted", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notify_admin_boleto_generated", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notify_admin_boleto_cancelled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notify_admin_cycle_request", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        # Admin WhatsApp numbers
        sa.Column("admin_whatsapp_numbers", sa.Text(), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("company_id", name="uq_notif_settings_company"),
    )


def downgrade() -> None:
    op.drop_table("company_notification_settings")
    # Note: PostgreSQL does not support removing enum values; downgrade omits enum rollback.
