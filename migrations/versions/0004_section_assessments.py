"""Rapports détaillés et simulations avec lien vers le rapport d'origine."""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "assessments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("case_kind", sa.String(20), nullable=False),
        sa.Column("parent_id", sa.String(36), sa.ForeignKey("assessments.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
    )
    op.create_index("ix_assessments_case_id", "assessments", ["case_id"])


def downgrade():
    op.drop_table("assessments")
