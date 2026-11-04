"""Éditions imprimables privées, publication explicite et cloisonnement institutionnel."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cases", sa.Column("institution_id", sa.String(100), nullable=True))
    op.create_table(
        "print_editions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("case_kind", sa.String(20), nullable=False),
        sa.Column("template_id", sa.String(60), nullable=False),
        sa.Column("audience", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("assessment_id", sa.String(36), sa.ForeignKey("assessments.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("author_id", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("html_content", sa.Text(), nullable=True),
        sa.Column("pdf_content", sa.LargeBinary(), nullable=True),
        sa.UniqueConstraint(
            "case_id", "template_id", "audience", "version", name="uq_print_version"
        ),
    )
    op.create_index("ix_print_editions_case_id", "print_editions", ["case_id"])
    op.create_table(
        "print_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("edition_id", sa.String(36), sa.ForeignKey("print_editions.id"), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_print_events_edition_id", "print_events", ["edition_id"])
    op.create_table(
        "print_publications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("assessment_id", sa.String(36), sa.ForeignKey("assessments.id"), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
    )
    op.create_index("ix_print_publications_assessment_id", "print_publications", ["assessment_id"])


def downgrade():
    op.drop_table("print_publications")
    op.drop_table("print_events")
    op.drop_table("print_editions")
    op.drop_column("cases", "institution_id")
