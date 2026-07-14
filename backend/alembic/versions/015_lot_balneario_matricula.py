"""Add balneário and matrícula (registration number) to lots.

Adds two lot-level fields collected on the lot registration screens (wizard and
traditional) and enforces that the matrícula (cartório registration number) is
unique per company, preventing duplicate terrenos.

Revision ID: 015_lot_balneario_matricula
Revises: 014_notification_settings
Create Date: 2026-07-14
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "015_lot_balneario_matricula"
down_revision = "014_notification_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lots",
        sa.Column(
            "balneario",
            sa.String(120),
            nullable=True,
            comment="Balneário / localidade do terreno",
        ),
    )
    op.add_column(
        "lots",
        sa.Column(
            "registration_number",
            sa.String(60),
            nullable=True,
            comment="Número de matrícula do imóvel (registro de cartório)",
        ),
    )

    # Matrícula única por empresa. Índice parcial para não conflitar com lotes
    # legados que ainda não têm matrícula preenchida (registration_number NULL).
    op.create_index(
        "uq_lots_company_registration",
        "lots",
        ["company_id", "registration_number"],
        unique=True,
        postgresql_where=sa.text("registration_number IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_lots_company_registration", table_name="lots")
    op.drop_column("lots", "registration_number")
    op.drop_column("lots", "balneario")
