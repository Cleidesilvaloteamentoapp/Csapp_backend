
"""Add client_documents, service_requests, service_request_messages, notifications tables.

Revision ID: 005_client_portal
Revises: 004_contract_features
Create Date: 2026-03-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision = "005_client_portal"
down_revision = "004_contract_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- PostgreSQL enum types ---
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE document_type AS ENUM (
                'RG', 'CPF', 'COMPROVANTE_RESIDENCIA', 'CNH', 'CONTRATO', 'OUTROS'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE document_status AS ENUM (
                'PENDING_REVIEW', 'APPROVED', 'REJECTED', 'EXPIRED'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE service_request_type AS ENUM (
                'MANUTENCAO', 'SUPORTE', 'FINANCEIRO', 'DOCUMENTACAO', 'OUTROS'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE service_request_status AS ENUM (
                'OPEN', 'IN_PROGRESS', 'WAITING_CLIENT', 'RESOLVED', 'CLOSED'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE service_request_priority AS ENUM (
                'LOW', 'MEDIUM', 'HIGH', 'URGENT'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE notification_type AS ENUM (
                'BOLETO_EMITIDO', 'BOLETO_VENCIDO', 'PAGAMENTO_CONFIRMADO',
                'DOCUMENTO_APROVADO', 'DOCUMENTO_REJEITADO',
                'SOLICITACAO_ATUALIZADA', 'GERAL'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # --- client_documents ---
    op.create_table(
        "client_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_type", sa.Enum("RG", "CPF", "COMPROVANTE_RESIDENCIA", "CNH", "CONTRATO", "OUTROS", name="document_type", create_constraint=False), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_size", sa.Integer, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.Enum("PENDING_REVIEW", "APPROVED", "REJECTED", "EXPIRED", name="document_status", create_constraint=False), nullable=False, server_default="PENDING_REVIEW"),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", UUID(as_uuid=True), sa.ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_client_documents_client", "client_documents", ["client_id"])
    op.create_index("idx_client_documents_company", "client_documents", ["company_id"])
    op.create_index("idx_client_documents_status", "client_documents", ["status"])
    op.create_index("idx_client_documents_type", "client_documents", ["document_type"])

    # --- service_requests ---
    op.create_table(
        "service_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ticket_number", sa.String(50), unique=True, nullable=False),
        sa.Column("service_type", sa.Enum("MANUTENCAO", "SUPORTE", "FINANCEIRO", "DOCUMENTACAO", "OUTROS", name="service_request_type", create_constraint=False), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("status", sa.Enum("OPEN", "IN_PROGRESS", "WAITING_CLIENT", "RESOLVED", "CLOSED", name="service_request_status", create_constraint=False), nullable=False, server_default="OPEN"),
        sa.Column("priority", sa.Enum("LOW", "MEDIUM", "HIGH", "URGENT", name="service_request_priority", create_constraint=False), nullable=False, server_default="MEDIUM"),
        sa.Column("assigned_to", UUID(as_uuid=True), sa.ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_service_requests_client", "service_requests", ["client_id"])
    op.create_index("idx_service_requests_company", "service_requests", ["company_id"])
    op.create_index("idx_service_requests_status", "service_requests", ["status"])
    op.create_index("idx_service_requests_ticket", "service_requests", ["ticket_number"])
    op.create_index("idx_service_requests_priority", "service_requests", ["priority"])

    # --- service_request_messages ---
    op.create_table(
        "service_request_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("request_id", UUID(as_uuid=True), sa.ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", UUID(as_uuid=True), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_type", sa.String(20), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("is_internal", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_sr_messages_request", "service_request_messages", ["request_id"])

    # --- notifications ---
    op.create_table(
        "notifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("type", sa.Enum("BOLETO_EMITIDO", "BOLETO_VENCIDO", "PAGAMENTO_CONFIRMADO", "DOCUMENTO_APROVADO", "DOCUMENTO_REJEITADO", "SOLICITACAO_ATUALIZADA", "GERAL", name="notification_type", create_constraint=False), nullable=False, server_default="GERAL"),
        sa.Column("is_read", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("data", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_notifications_user", "notifications", ["user_id"])
    op.create_index("idx_notifications_company", "notifications", ["company_id"])
    op.create_index("idx_notifications_read", "notifications", ["is_read"])
    op.create_index("idx_notifications_type", "notifications", ["type"])
    op.create_index("idx_notifications_user_read", "notifications", ["user_id", "is_read"])


def downgrade() -> None:
    op.drop_table("service_request_messages")
    op.drop_table("service_requests")
    op.drop_table("client_documents")
    op.drop_table("notifications")

    op.execute("DROP TYPE IF EXISTS document_type")
    op.execute("DROP TYPE IF EXISTS document_status")
    op.execute("DROP TYPE IF EXISTS service_request_type")
    op.execute("DROP TYPE IF EXISTS service_request_status")
    op.execute("DROP TYPE IF EXISTS service_request_priority")
    op.execute("DROP TYPE IF EXISTS notification_type")
