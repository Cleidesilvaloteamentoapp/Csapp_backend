
"""Add contract fields, contract_history, renegotiations, rescissions tables.

Revision ID: 004_contract_features
Revises: 003_add_boletos
Create Date: 2026-03-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision = "004_contract_features"
down_revision = "003_add_boletos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # 1. New enum types
    # -----------------------------------------------------------------------
    op.execute("""
        CREATE TYPE contract_event_type AS ENUM (
            'PAYMENT', 'OVERDUE', 'RENEGOTIATION', 'ADJUSTMENT',
            'MANUAL_WRITEOFF', 'DISCOUNT_APPLIED', 'PENALTY_REMOVED',
            'BOLETO_ISSUED', 'BOLETO_CANCELLED', 'SECOND_COPY',
            'RESCISSION_STARTED', 'RESCISSION_COMPLETED',
            'STATUS_CHANGE', 'NOTE'
        )
    """)
    op.execute("""
        CREATE TYPE renegotiation_status AS ENUM (
            'DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'APPLIED', 'CANCELLED'
        )
    """)
    op.execute("""
        CREATE TYPE rescission_status AS ENUM (
            'REQUESTED', 'PENDING_APPROVAL', 'APPROVED', 'COMPLETED', 'CANCELLED'
        )
    """)

    # Extend existing enums with new values
    op.execute("ALTER TYPE client_status ADD VALUE IF NOT EXISTS 'IN_NEGOTIATION'")
    op.execute("ALTER TYPE client_status ADD VALUE IF NOT EXISTS 'RESCINDED'")
    op.execute("ALTER TYPE client_lot_status ADD VALUE IF NOT EXISTS 'RESCINDED'")
    op.execute("ALTER TYPE boleto_status ADD VALUE IF NOT EXISTS 'PENDING_APPROVAL'")

    # -----------------------------------------------------------------------
    # 2. Add new columns to clients
    # -----------------------------------------------------------------------
    op.add_column("clients", sa.Column("contract_number", sa.String(50), nullable=True))
    op.add_column("clients", sa.Column("matricula", sa.String(50), nullable=True))
    op.add_column("clients", sa.Column("notes", sa.Text(), nullable=True))
    op.create_index("idx_clients_contract_number", "clients", ["contract_number"], unique=True)
    op.create_index("idx_clients_matricula", "clients", ["matricula"])

    # -----------------------------------------------------------------------
    # 3. Add new columns to client_lots
    # -----------------------------------------------------------------------
    op.add_column("client_lots", sa.Column("down_payment", sa.Numeric(14, 2), nullable=True, server_default="0"))
    op.add_column("client_lots", sa.Column("total_installments", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("client_lots", sa.Column("current_cycle", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("client_lots", sa.Column("current_installment_value", sa.Numeric(14, 2), nullable=True))
    op.add_column("client_lots", sa.Column("annual_adjustment_rate", sa.Numeric(6, 4), nullable=True, server_default="0.0500"))
    op.add_column("client_lots", sa.Column("last_adjustment_date", sa.Date(), nullable=True))
    op.add_column("client_lots", sa.Column("last_cycle_paid_at", sa.Date(), nullable=True))

    # -----------------------------------------------------------------------
    # 4. Create contract_history table
    # -----------------------------------------------------------------------
    op.create_table(
        "contract_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("client_lot_id", UUID(as_uuid=True), sa.ForeignKey("client_lots.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("invoice_id", UUID(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("boleto_id", UUID(as_uuid=True), sa.ForeignKey("boletos.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.Enum(
            'PAYMENT', 'OVERDUE', 'RENEGOTIATION', 'ADJUSTMENT',
            'MANUAL_WRITEOFF', 'DISCOUNT_APPLIED', 'PENALTY_REMOVED',
            'BOLETO_ISSUED', 'BOLETO_CANCELLED', 'SECOND_COPY',
            'RESCISSION_STARTED', 'RESCISSION_COMPLETED',
            'STATUS_CHANGE', 'NOTE',
            name="contract_event_type", create_type=False
        ), nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("previous_value", sa.String(500), nullable=True),
        sa.Column("new_value", sa.String(500), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("performed_by", UUID(as_uuid=True), sa.ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_contract_history_client_type", "contract_history", ["client_id", "event_type"])
    op.create_index("idx_contract_history_company_created", "contract_history", ["company_id", "created_at"])

    # -----------------------------------------------------------------------
    # 5. Create renegotiations table
    # -----------------------------------------------------------------------
    op.create_table(
        "renegotiations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("client_lot_id", UUID(as_uuid=True), sa.ForeignKey("client_lots.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("status", sa.Enum(
            'DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'APPLIED', 'CANCELLED',
            name="renegotiation_status", create_type=False
        ), nullable=False, server_default="DRAFT", index=True),
        sa.Column("original_debt_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("overdue_invoices_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("penalty_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("interest_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("discount_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("penalty_waived", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("interest_waived", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("final_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("new_installments", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_due_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("cancelled_invoice_ids", JSONB, nullable=True),
        sa.Column("cancelled_boleto_ids", JSONB, nullable=True),
        sa.Column("new_invoice_ids", JSONB, nullable=True),
        sa.Column("approved_by", UUID(as_uuid=True), sa.ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("profiles.id", ondelete="SET NULL"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # -----------------------------------------------------------------------
    # 6. Create rescissions table
    # -----------------------------------------------------------------------
    op.create_table(
        "rescissions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("client_lot_id", UUID(as_uuid=True), sa.ForeignKey("client_lots.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("status", sa.Enum(
            'REQUESTED', 'PENDING_APPROVAL', 'APPROVED', 'COMPLETED', 'CANCELLED',
            name="rescission_status", create_type=False
        ), nullable=False, server_default="REQUESTED", index=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("total_paid", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("total_debt", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("refund_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("penalty_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("request_date", sa.Date(), nullable=False),
        sa.Column("approval_date", sa.Date(), nullable=True),
        sa.Column("completion_date", sa.Date(), nullable=True),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("document_path", sa.Text(), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("requested_by", UUID(as_uuid=True), sa.ForeignKey("profiles.id", ondelete="SET NULL"), nullable=False),
        sa.Column("approved_by", UUID(as_uuid=True), sa.ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("rescissions")
    op.drop_table("renegotiations")
    op.drop_table("contract_history")

    # Remove client_lots columns
    op.drop_column("client_lots", "last_cycle_paid_at")
    op.drop_column("client_lots", "last_adjustment_date")
    op.drop_column("client_lots", "annual_adjustment_rate")
    op.drop_column("client_lots", "current_installment_value")
    op.drop_column("client_lots", "current_cycle")
    op.drop_column("client_lots", "total_installments")
    op.drop_column("client_lots", "down_payment")

    # Remove client columns
    op.drop_index("idx_clients_matricula", table_name="clients")
    op.drop_index("idx_clients_contract_number", table_name="clients")
    op.drop_column("clients", "notes")
    op.drop_column("clients", "matricula")
    op.drop_column("clients", "contract_number")

    # Drop new enum types
    op.execute("DROP TYPE rescission_status")
    op.execute("DROP TYPE renegotiation_status")
    op.execute("DROP TYPE contract_event_type")
