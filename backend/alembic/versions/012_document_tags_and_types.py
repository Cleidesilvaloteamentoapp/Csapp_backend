"""Document tags + expanded DocumentType enum.

Adds a `tags` text[] column to client_documents and extends the
`document_type` enum with additional real-estate document categories.

Revision ID: 012_document_tags_and_types
Revises: 011_staff_permissions
Create Date: 2026-05-15
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "012_document_tags_and_types"
down_revision = "011_staff_permissions"
branch_labels = None
depends_on = None


NEW_DOCUMENT_TYPES = [
    "CERTIDAO_ESTADO_CIVIL",
    "COMPROVANTE_RENDA",
    "MATRICULA",
    "GUIA_INFORMACAO",
    "IPTU",
    "FOTOS_IMOVEL",
]


def upgrade() -> None:
    # Add new enum values to document_type. Each ADD VALUE must be its own
    # statement and outside a transaction; Alembic 1.13 handles that with
    # autocommit_block.
    with op.get_context().autocommit_block():
        for value in NEW_DOCUMENT_TYPES:
            op.execute(
                f"ALTER TYPE document_type ADD VALUE IF NOT EXISTS '{value}'"
            )

    # Add tags column as text[] with empty-array default for existing rows.
    op.add_column(
        "client_documents",
        sa.Column(
            "tags",
            sa.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
            comment="Free-form classification tags (e.g. 'urgente', 'assinado').",
        ),
    )

    # GIN index for fast tag filtering.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_client_documents_tags "
        "ON client_documents USING GIN (tags)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_client_documents_tags")
    op.drop_column("client_documents", "tags")
    # Postgres does not support removing enum values cleanly without
    # recreating the type — leaving the extra DocumentType values in place
    # is safe (the application enum already enumerates them).
