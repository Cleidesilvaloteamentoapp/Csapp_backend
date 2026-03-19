
"""Add boleto tags, per-lot financial rules, economic indices, cycle approvals,
contract transfers, early payoff requests, and writeoff tracking.

Revision ID: 006_client_adjustments
Revises: 005_client_portal
Create Date: 2026-03-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision = "006_client_adjustments"
down_revision = "005_client_portal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # 1. New PostgreSQL enum types
    # -----------------------------------------------------------------------
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE boleto_tag AS ENUM (
                'ENTRADA_PARCELADA', 'PARCELA_CONTRATO', 'SERVICO_AVULSO',
                'SEGUNDA_VIA', 'RENEGOCIACAO'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE writeoff_type AS ENUM ('AUTOMATICA_BANCO', 'MANUAL_ADMIN');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE adjustment_index AS ENUM ('IPCA', 'IGPM', 'CUB', 'INPC');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE adjustment_frequency AS ENUM (
                'MONTHLY', 'QUARTERLY', 'SEMIANNUAL', 'ANNUAL'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE cycle_approval_status AS ENUM ('PENDING', 'APPROVED', 'REJECTED');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE transfer_status AS ENUM (
                'PENDING', 'APPROVED', 'COMPLETED', 'CANCELLED'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE early_payoff_status AS ENUM (
                'PENDING', 'CONTACTED', 'COMPLETED', 'CANCELLED'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE index_source AS ENUM ('MANUAL', 'BCB_API');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # Add BAIXA_MANUAL to boleto_status if not present
    op.execute("""
        DO $$ BEGIN
            ALTER TYPE boleto_status ADD VALUE IF NOT EXISTS 'BAIXA_MANUAL';
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # Add new notification types
    op.execute("""
        DO $$ BEGIN
            ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'CICLO_PENDENTE';
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'TRANSFERENCIA_CONTRATO';
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'ANTECIPACAO_SOLICITADA';
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'DISTRATO_AUTOMATICO';
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # Add new contract event types
    for val in ('TRANSFER', 'AUTO_RESCISSION', 'CYCLE_APPROVED', 'EARLY_PAYOFF_REQUEST'):
        op.execute(f"""
            DO $$ BEGIN
                ALTER TYPE contract_event_type ADD VALUE IF NOT EXISTS '{val}';
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """)

    # -----------------------------------------------------------------------
    # 2. ALTER boletos – add tag, installment_label, writeoff columns
    # -----------------------------------------------------------------------
    op.add_column("boletos", sa.Column(
        "tag", sa.Enum("ENTRADA_PARCELADA", "PARCELA_CONTRATO", "SERVICO_AVULSO",
                       "SEGUNDA_VIA", "RENEGOCIACAO", name="boleto_tag",
                       create_constraint=False),
        nullable=True,
    ))
    op.add_column("boletos", sa.Column("installment_label", sa.String(50), nullable=True))
    op.add_column("boletos", sa.Column(
        "writeoff_type", sa.Enum("AUTOMATICA_BANCO", "MANUAL_ADMIN",
                                 name="writeoff_type", create_constraint=False),
        nullable=True,
    ))
    op.add_column("boletos", sa.Column(
        "writeoff_by", UUID(as_uuid=True),
        sa.ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True,
    ))
    op.add_column("boletos", sa.Column("writeoff_reason", sa.Text(), nullable=True))
    op.create_index("ix_boletos_tag", "boletos", ["tag"])

    # -----------------------------------------------------------------------
    # 3. ALTER client_lots – add per-lot financial rule columns + transfer history
    # -----------------------------------------------------------------------
    op.add_column("client_lots", sa.Column(
        "penalty_rate", sa.Numeric(6, 4), nullable=True,
        comment="Custom penalty rate overriding system default 0.02 (2%)",
    ))
    op.add_column("client_lots", sa.Column(
        "daily_interest_rate", sa.Numeric(8, 6), nullable=True,
        comment="Custom daily interest rate overriding default 0.00033",
    ))
    op.add_column("client_lots", sa.Column(
        "adjustment_index",
        sa.Enum("IPCA", "IGPM", "CUB", "INPC", name="adjustment_index",
                create_constraint=False),
        nullable=True,
        comment="Price index for adjustments",
    ))
    op.add_column("client_lots", sa.Column(
        "adjustment_frequency",
        sa.Enum("MONTHLY", "QUARTERLY", "SEMIANNUAL", "ANNUAL",
                name="adjustment_frequency", create_constraint=False),
        nullable=True,
        comment="How often adjustments are applied",
    ))
    op.add_column("client_lots", sa.Column(
        "adjustment_custom_rate", sa.Numeric(6, 4), nullable=True,
        comment="Custom fixed rate overriding default 5% annual",
    ))
    op.add_column("client_lots", sa.Column(
        "previous_client_id", UUID(as_uuid=True),
        sa.ForeignKey("clients.id", ondelete="SET NULL"), nullable=True,
        comment="Previous owner after a contract transfer",
    ))
    op.add_column("client_lots", sa.Column(
        "transfer_date", sa.Date(), nullable=True,
        comment="Date of the last ownership transfer",
    ))

    # -----------------------------------------------------------------------
    # 4. New table: economic_indices
    # -----------------------------------------------------------------------
    op.create_table(
        "economic_indices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("index_type",
                  sa.Enum("IPCA", "IGPM", "CUB", "INPC", name="adjustment_index",
                          create_constraint=False),
                  nullable=False, index=True),
        sa.Column("state_code", sa.String(2), nullable=True, index=True),
        sa.Column("reference_month", sa.Date(), nullable=False, index=True),
        sa.Column("value", sa.Numeric(10, 6), nullable=False),
        sa.Column("source",
                  sa.Enum("MANUAL", "BCB_API", name="index_source",
                          create_constraint=False),
                  nullable=False, server_default="MANUAL"),
        sa.Column("created_by", UUID(as_uuid=True),
                  sa.ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    # -----------------------------------------------------------------------
    # 5. New table: cycle_approvals
    # -----------------------------------------------------------------------
    op.create_table(
        "cycle_approvals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("client_lot_id", UUID(as_uuid=True),
                  sa.ForeignKey("client_lots.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("cycle_number", sa.Integer(), nullable=False),
        sa.Column("status",
                  sa.Enum("PENDING", "APPROVED", "REJECTED",
                          name="cycle_approval_status", create_constraint=False),
                  nullable=False, server_default="PENDING", index=True),
        sa.Column("previous_installment_value", sa.Numeric(14, 2), nullable=False),
        sa.Column("new_installment_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("adjustment_details", JSONB, nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", UUID(as_uuid=True),
                  sa.ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    # -----------------------------------------------------------------------
    # 6. New table: contract_transfers
    # -----------------------------------------------------------------------
    op.create_table(
        "contract_transfers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("client_lot_id", UUID(as_uuid=True),
                  sa.ForeignKey("client_lots.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("from_client_id", UUID(as_uuid=True),
                  sa.ForeignKey("clients.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("to_client_id", UUID(as_uuid=True),
                  sa.ForeignKey("clients.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("status",
                  sa.Enum("PENDING", "APPROVED", "COMPLETED", "CANCELLED",
                          name="transfer_status", create_constraint=False),
                  nullable=False, server_default="PENDING", index=True),
        sa.Column("transfer_fee", sa.Numeric(14, 2), nullable=True, server_default="0"),
        sa.Column("transfer_date", sa.Date(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("documents", JSONB, nullable=True),
        sa.Column("requested_by", UUID(as_uuid=True),
                  sa.ForeignKey("profiles.id", ondelete="SET NULL"), nullable=False),
        sa.Column("approved_by", UUID(as_uuid=True),
                  sa.ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    # -----------------------------------------------------------------------
    # 7. New table: early_payoff_requests
    # -----------------------------------------------------------------------
    op.create_table(
        "early_payoff_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("client_id", UUID(as_uuid=True),
                  sa.ForeignKey("clients.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("client_lot_id", UUID(as_uuid=True),
                  sa.ForeignKey("client_lots.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("status",
                  sa.Enum("PENDING", "CONTACTED", "COMPLETED", "CANCELLED",
                          name="early_payoff_status", create_constraint=False),
                  nullable=False, server_default="PENDING", index=True),
        sa.Column("requested_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("client_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("early_payoff_requests")
    op.drop_table("contract_transfers")
    op.drop_table("cycle_approvals")
    op.drop_table("economic_indices")

    # Remove columns from client_lots
    for col in ("transfer_date", "previous_client_id", "adjustment_custom_rate",
                "adjustment_frequency", "adjustment_index", "daily_interest_rate",
                "penalty_rate"):
        op.drop_column("client_lots", col)

    # Remove columns from boletos
    op.drop_index("ix_boletos_tag", table_name="boletos")
    for col in ("writeoff_reason", "writeoff_by", "writeoff_type",
                "installment_label", "tag"):
        op.drop_column("boletos", col)

    # Drop enum types
    for t in ("index_source", "early_payoff_status", "transfer_status",
              "cycle_approval_status", "adjustment_frequency",
              "adjustment_index", "writeoff_type", "boleto_tag"):
        op.execute(f"DROP TYPE IF EXISTS {t}")
