"""Cycle renewal panel: integrity, early trigger fields and deed checklist.

The renewal flow only raised an approval once all 12 boletos of a cycle were
LIQUIDADO, so a single unpaid installment hid the renewal forever. The panel now
surfaces the cycle ahead of time and carries the settlement picture with it, so
an admin can see *why* a renewal is blocked and override it deliberately.

Adds to ``cycle_approvals``: the settlement snapshot (``unpaid_count``,
``overdue_amount``), the final-cycle marker that starts escrituração, and the
forced-renewal audit trail. Also adds the unique ``(client_lot_id,
cycle_number)`` constraint the duplicate-guard was only enforcing in Python.

NOTA DE DEPLOY: em produção o schema é aplicado à mão pelo SQL Editor do
Supabase, não por `alembic upgrade` (não há create_all nem upgrade no boot --
ver entrypoint.sh). O equivalente desta migração está em
``sql/024_cycle_renewal_panel.sql`` e é ele que roda em produção. Mantenha os
dois em sincronia.

Revision ID: 019_cycle_renewal_panel
Revises: 018_company_branding
Create Date: 2026-09-25
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision = "019_cycle_renewal_panel"
down_revision = "018_company_branding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- cycle_approvals: settlement snapshot + final cycle + forced override ---
    op.add_column(
        "cycle_approvals",
        sa.Column(
            "is_final_cycle",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="Last cycle of the contract; triggers the escrituração alert",
        ),
    )
    op.add_column(
        "cycle_approvals",
        sa.Column("unpaid_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "cycle_approvals",
        sa.Column(
            "overdue_amount",
            sa.Numeric(14, 2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "cycle_approvals",
        sa.Column("forced", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("cycle_approvals", sa.Column("forced_reason", sa.Text(), nullable=True))
    op.add_column(
        "cycle_approvals",
        sa.Column(
            "forced_by",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # Collapse pre-existing duplicates before the constraint can be trusted.
    op.execute(
        """
        DELETE FROM cycle_approvals a
        USING cycle_approvals b
        WHERE a.client_lot_id = b.client_lot_id
          AND a.cycle_number = b.cycle_number
          AND a.ctid > b.ctid
        """
    )
    op.create_unique_constraint(
        "uq_cycle_approvals_lot_cycle",
        "cycle_approvals",
        ["client_lot_id", "cycle_number"],
    )

    # --- deed checklists (escrituração) ---
    op.create_table(
        "deed_checklists",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "client_lot_id",
            UUID(as_uuid=True),
            sa.ForeignKey("client_lots.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "items",
            JSONB,
            nullable=False,
            server_default="[]",
            comment="[{document_type, label, done, note, updated_at}]",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # --- new notification type for the escrituração alert ---
    # ALTER TYPE ... ADD VALUE cannot be used in the transaction that adds it.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'ESCRITURACAO_PENDENTE'"
        )


def downgrade() -> None:
    op.drop_table("deed_checklists")
    op.drop_constraint("uq_cycle_approvals_lot_cycle", "cycle_approvals", type_="unique")
    for col in (
        "forced_by",
        "forced_reason",
        "forced",
        "overdue_amount",
        "unpaid_count",
        "is_final_cycle",
    ):
        op.drop_column("cycle_approvals", col)
    # PostgreSQL cannot drop a value from an enum type; ESCRITURACAO_PENDENTE stays.
