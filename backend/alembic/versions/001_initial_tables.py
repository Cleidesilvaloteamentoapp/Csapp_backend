"""Create all initial tables

Revision ID: 001_initial
Revises: None
Create Date: 2026-02-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- ENUM types ---
    company_status = postgresql.ENUM("active", "suspended", "inactive", name="company_status", create_type=False)
    user_role = postgresql.ENUM("super_admin", "company_admin", "client", name="user_role", create_type=False)
    client_status = postgresql.ENUM("active", "inactive", "defaulter", name="client_status", create_type=False)
    lot_status = postgresql.ENUM("available", "reserved", "sold", name="lot_status", create_type=False)
    client_lot_status = postgresql.ENUM("active", "completed", "cancelled", name="client_lot_status", create_type=False)
    invoice_status = postgresql.ENUM("pending", "paid", "overdue", "cancelled", name="invoice_status", create_type=False)
    service_order_status = postgresql.ENUM("requested", "approved", "in_progress", "completed", "cancelled", name="service_order_status", create_type=False)
    referral_status = postgresql.ENUM("pending", "contacted", "converted", "lost", name="referral_status", create_type=False)

    op.execute("CREATE TYPE company_status AS ENUM ('active', 'suspended', 'inactive')")
    op.execute("CREATE TYPE user_role AS ENUM ('super_admin', 'company_admin', 'client')")
    op.execute("CREATE TYPE client_status AS ENUM ('active', 'inactive', 'defaulter')")
    op.execute("CREATE TYPE lot_status AS ENUM ('available', 'reserved', 'sold')")
    op.execute("CREATE TYPE client_lot_status AS ENUM ('active', 'completed', 'cancelled')")
    op.execute("CREATE TYPE invoice_status AS ENUM ('pending', 'paid', 'overdue', 'cancelled')")
    op.execute("CREATE TYPE service_order_status AS ENUM ('requested', 'approved', 'in_progress', 'completed', 'cancelled')")
    op.execute("CREATE TYPE referral_status AS ENUM ('pending', 'contacted', 'converted', 'lost')")

    # --- companies ---
    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("settings", postgresql.JSONB, nullable=True),
        sa.Column("status", company_status, nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_companies_slug", "companies", ["slug"], unique=True)
    op.create_index("ix_companies_status", "companies", ["status"])

    # --- profiles ---
    op.create_table(
        "profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("cpf_cnpj", sa.String(20), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_profiles_company_id", "profiles", ["company_id"])
    op.create_index("ix_profiles_role", "profiles", ["role"])
    op.create_index("ix_profiles_cpf_cnpj", "profiles", ["cpf_cnpj"], unique=True)
    op.create_index("ix_profiles_email", "profiles", ["email"])

    # --- clients ---
    op.create_table(
        "clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("cpf_cnpj", sa.String(20), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("address", postgresql.JSONB, nullable=True),
        sa.Column("documents", postgresql.JSONB, nullable=True),
        sa.Column("status", client_status, nullable=False, server_default="active"),
        sa.Column("asaas_customer_id", sa.String(255), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_clients_company_id", "clients", ["company_id"])
    op.create_index("ix_clients_email", "clients", ["email"])
    op.create_index("ix_clients_cpf_cnpj", "clients", ["cpf_cnpj"])
    op.create_index("ix_clients_status", "clients", ["status"])

    # --- developments ---
    op.create_table(
        "developments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column("documents", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_developments_company_id", "developments", ["company_id"])

    # --- lots ---
    op.create_table(
        "lots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("development_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("developments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lot_number", sa.String(50), nullable=False),
        sa.Column("block", sa.String(50), nullable=True),
        sa.Column("area_m2", sa.Numeric(12, 2), nullable=False),
        sa.Column("price", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", lot_status, nullable=False, server_default="available"),
        sa.Column("documents", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_lots_company_id", "lots", ["company_id"])
    op.create_index("ix_lots_status", "lots", ["status"])

    # --- client_lots ---
    op.create_table(
        "client_lots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purchase_date", sa.Date, nullable=False),
        sa.Column("total_value", sa.Numeric(14, 2), nullable=False),
        sa.Column("payment_plan", postgresql.JSONB, nullable=True),
        sa.Column("status", client_lot_status, nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_client_lots_company_id", "client_lots", ["company_id"])
    op.create_index("ix_client_lots_status", "client_lots", ["status"])

    # --- invoices ---
    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_lot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("client_lots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("due_date", sa.Date, nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("installment_number", sa.Integer, nullable=False),
        sa.Column("status", invoice_status, nullable=False, server_default="pending"),
        sa.Column("asaas_payment_id", sa.String(255), nullable=True),
        sa.Column("barcode", sa.String(255), nullable=True),
        sa.Column("payment_url", sa.String(500), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_invoices_company_id", "invoices", ["company_id"])
    op.create_index("ix_invoices_due_date", "invoices", ["due_date"])
    op.create_index("ix_invoices_status", "invoices", ["status"])

    # --- service_types ---
    op.create_table(
        "service_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("base_price", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_service_types_company_id", "service_types", ["company_id"])

    # --- service_orders ---
    op.create_table(
        "service_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("service_type_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("service_types.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_date", sa.Date, nullable=False),
        sa.Column("execution_date", sa.Date, nullable=True),
        sa.Column("status", service_order_status, nullable=False, server_default="requested"),
        sa.Column("cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("revenue", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_service_orders_company_id", "service_orders", ["company_id"])
    op.create_index("ix_service_orders_status", "service_orders", ["status"])

    # --- referrals ---
    op.create_table(
        "referrals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("referrer_client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("referred_name", sa.String(255), nullable=False),
        sa.Column("referred_phone", sa.String(20), nullable=False),
        sa.Column("referred_email", sa.String(255), nullable=True),
        sa.Column("status", referral_status, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_referrals_company_id", "referrals", ["company_id"])
    op.create_index("ix_referrals_status", "referrals", ["status"])

    # --- audit_logs ---
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("table_name", sa.String(100), nullable=False),
        sa.Column("operation", sa.String(20), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # --- updated_at trigger function ---
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Apply trigger to all tables with updated_at
    for table in [
        "companies", "profiles", "clients", "developments", "lots",
        "client_lots", "invoices", "service_types", "service_orders", "referrals",
    ]:
        op.execute(f"""
            CREATE TRIGGER trg_{table}_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        """)


def downgrade() -> None:
    # Drop triggers
    for table in [
        "referrals", "service_orders", "service_types", "invoices",
        "client_lots", "lots", "developments", "clients", "profiles", "companies",
    ]:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table}")

    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")

    # Drop tables in reverse dependency order
    op.drop_table("audit_logs")
    op.drop_table("referrals")
    op.drop_table("service_orders")
    op.drop_table("service_types")
    op.drop_table("invoices")
    op.drop_table("client_lots")
    op.drop_table("lots")
    op.drop_table("developments")
    op.drop_table("clients")
    op.drop_table("profiles")
    op.drop_table("companies")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS referral_status")
    op.execute("DROP TYPE IF EXISTS service_order_status")
    op.execute("DROP TYPE IF EXISTS invoice_status")
    op.execute("DROP TYPE IF EXISTS client_lot_status")
    op.execute("DROP TYPE IF EXISTS lot_status")
    op.execute("DROP TYPE IF EXISTS client_status")
    op.execute("DROP TYPE IF EXISTS user_role")
    op.execute("DROP TYPE IF EXISTS company_status")
