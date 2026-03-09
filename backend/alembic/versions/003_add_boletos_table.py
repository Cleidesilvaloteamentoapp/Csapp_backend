
"""Add boletos table for Sicredi boleto records linked to clients.

Revision ID: 003_add_boletos
Revises: 002_sicredi_creds
Create Date: 2026-03-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision = "003_add_boletos"
down_revision = "002_sicredi_creds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create boleto_status enum
    op.execute("""
        CREATE TYPE boleto_status AS ENUM (
            'NORMAL',
            'LIQUIDADO',
            'VENCIDO',
            'CANCELADO'
        )
    """)

    op.create_table(
        "boletos",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True),
        
        # Sicredi identifiers
        sa.Column("nosso_numero", sa.String(50), nullable=False, unique=True, index=True),
        sa.Column("seu_numero", sa.String(50), nullable=False, index=True),
        sa.Column("linha_digitavel", sa.String(100), nullable=True),
        sa.Column("codigo_barras", sa.String(100), nullable=True),
        
        # Boleto type and document
        sa.Column("tipo_cobranca", sa.String(20), nullable=False),
        sa.Column("especie_documento", sa.String(50), nullable=False),
        
        # Dates
        sa.Column("data_vencimento", sa.Date(), nullable=False, index=True),
        sa.Column("data_emissao", sa.Date(), nullable=False, index=True),
        sa.Column("data_liquidacao", sa.Date(), nullable=True),
        
        # Values
        sa.Column("valor", sa.Numeric(12, 2), nullable=False),
        sa.Column("valor_liquidacao", sa.Numeric(12, 2), nullable=True),
        
        # Status
        sa.Column("status", sa.Enum("NORMAL", "LIQUIDADO", "VENCIDO", "CANCELADO", name="boleto_status", create_type=False), nullable=False, server_default="NORMAL", index=True),
        
        # Pix (for HIBRIDO type)
        sa.Column("txid", sa.String(100), nullable=True),
        sa.Column("qr_code", sa.Text(), nullable=True),
        
        # Optional link to invoice
        sa.Column("invoice_id", UUID(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True),
        
        # Store pagador data and full API response
        sa.Column("pagador_data", JSONB, nullable=True),
        sa.Column("raw_response", JSONB, nullable=True),
        
        # Audit
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True),
        
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Performance indexes for multi-tenant queries
    op.create_index("idx_boletos_company_client", "boletos", ["company_id", "client_id"])
    op.create_index("idx_boletos_company_status", "boletos", ["company_id", "status"])
    op.create_index("idx_boletos_company_vencimento", "boletos", ["company_id", "data_vencimento"])
    op.create_index("idx_boletos_seu_numero_company", "boletos", ["seu_numero", "company_id"])


def downgrade() -> None:
    op.drop_index("idx_boletos_seu_numero_company", table_name="boletos")
    op.drop_index("idx_boletos_company_vencimento", table_name="boletos")
    op.drop_index("idx_boletos_company_status", table_name="boletos")
    op.drop_index("idx_boletos_company_client", table_name="boletos")
    op.drop_table("boletos")
    op.execute("DROP TYPE boleto_status")
