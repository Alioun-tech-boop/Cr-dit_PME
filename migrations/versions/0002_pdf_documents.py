"""Pièces PDF et extractions brutes rattachées explicitement au dossier."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("case_kind", sa.String(20), nullable=False),
        sa.Column("document_type", sa.String(100), nullable=False),
        sa.Column("role", sa.String(120), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("document_sha256", sa.String(64), nullable=False),
        sa.Column("original_pdf", sa.LargeBinary(), nullable=False),
        sa.Column("extraction", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_documents_case_id", "documents", ["case_id"])


def downgrade():
    op.drop_table("documents")
