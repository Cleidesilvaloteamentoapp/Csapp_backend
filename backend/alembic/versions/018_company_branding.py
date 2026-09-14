"""Add company_branding table for per-company white-label identity.

Stores only the seed values of a company's visual identity: five brand colours,
the base border radius, three asset paths (Supabase Storage) and two wording
overrides. Every column is nullable — NULL means "use the platform default",
which lives in the frontend's globals.css. The remaining design tokens are
derived from these seeds on the client.

Revision ID: 018_company_branding
Revises: 017_writeoff_type_baixa_externa
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "018_company_branding"
down_revision = "017_writeoff_type_baixa_externa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_branding",
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
        # Seed colours (#RRGGBB)
        sa.Column("primary_color", sa.String(7), nullable=True),
        sa.Column("accent_color", sa.String(7), nullable=True),
        sa.Column("sidebar_color", sa.String(7), nullable=True),
        sa.Column("background_color", sa.String(7), nullable=True),
        sa.Column("success_color", sa.String(7), nullable=True),
        # Shape
        sa.Column("radius", sa.String(16), nullable=True),
        # Assets (storage paths, never URLs)
        sa.Column("logo_path", sa.Text(), nullable=True),
        sa.Column("favicon_path", sa.Text(), nullable=True),
        sa.Column("app_icon_path", sa.Text(), nullable=True),
        # Wording
        sa.Column("display_name", sa.String(60), nullable=True),
        sa.Column("tagline", sa.String(80), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("company_id", name="uq_company_branding_company"),
    )


def downgrade() -> None:
    op.drop_table("company_branding")
