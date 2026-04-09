"""Add property type fields to developments table.

Revision ID: 010_property_types
Revises: 009_add_paid_installments
Create Date: 2026-04-09
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "010_property_types"
down_revision = "009_add_paid_installments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add property_type column
    op.add_column(
        "developments",
        sa.Column(
            "property_type",
            sa.String(20),
            nullable=False,
            server_default="LOT",
            comment="Type of property: LOT, HOUSE, APARTMENT, COMMERCIAL, RURAL",
        ),
    )

    # Lot-specific fields
    op.add_column(
        "developments",
        sa.Column(
            "block",
            sa.String(50),
            nullable=True,
            comment="Block identifier for lots",
        ),
    )
    op.add_column(
        "developments",
        sa.Column(
            "lot_number",
            sa.String(50),
            nullable=True,
            comment="Lot number identifier",
        ),
    )
    op.add_column(
        "developments",
        sa.Column(
            "area_m2",
            sa.Numeric(10, 2),
            nullable=True,
            comment="Area in square meters (for lots and rural properties)",
        ),
    )

    # Residential-specific fields
    op.add_column(
        "developments",
        sa.Column(
            "bedrooms",
            sa.Integer(),
            nullable=True,
            comment="Number of bedrooms (for houses and apartments)",
        ),
    )
    op.add_column(
        "developments",
        sa.Column(
            "bathrooms",
            sa.Integer(),
            nullable=True,
            comment="Number of bathrooms (for houses and apartments)",
        ),
    )
    op.add_column(
        "developments",
        sa.Column(
            "suites",
            sa.Integer(),
            nullable=True,
            comment="Number of suites (for houses and apartments)",
        ),
    )
    op.add_column(
        "developments",
        sa.Column(
            "parking_spaces",
            sa.Integer(),
            nullable=True,
            comment="Number of parking spaces (for houses and apartments)",
        ),
    )
    op.add_column(
        "developments",
        sa.Column(
            "construction_area_m2",
            sa.Numeric(10, 2),
            nullable=True,
            comment="Construction area in square meters (for houses, apartments, commercial)",
        ),
    )
    op.add_column(
        "developments",
        sa.Column(
            "total_area_m2",
            sa.Numeric(10, 2),
            nullable=True,
            comment="Total area in square meters (for houses and apartments)",
        ),
    )

    # General fields
    op.add_column(
        "developments",
        sa.Column(
            "price",
            sa.Numeric(15, 2),
            nullable=True,
            comment="Property price",
        ),
    )

    # Create index on property_type for filtering
    op.create_index(
        "idx_developments_property_type",
        "developments",
        ["property_type"],
        postgresql_using="btree",
    )


def downgrade() -> None:
    # Drop index
    op.drop_index("idx_developments_property_type", table_name="developments")

    # Drop columns in reverse order
    op.drop_column("developments", "price")
    op.drop_column("developments", "total_area_m2")
    op.drop_column("developments", "construction_area_m2")
    op.drop_column("developments", "parking_spaces")
    op.drop_column("developments", "suites")
    op.drop_column("developments", "bathrooms")
    op.drop_column("developments", "bedrooms")
    op.drop_column("developments", "area_m2")
    op.drop_column("developments", "lot_number")
    op.drop_column("developments", "block")
    op.drop_column("developments", "property_type")
