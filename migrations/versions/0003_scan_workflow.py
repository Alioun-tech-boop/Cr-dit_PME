"""Dépôt, sources, dérivés, revue et propriétaire explicite des dossiers."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cases", sa.Column("owner_id", sa.String(100), nullable=True))
    op.create_table(
        "submissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("case_kind", sa.String(20), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
    )
    op.create_index("ix_submissions_case_id", "submissions", ["case_id"])
    op.create_table(
        "document_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("submission_id", sa.String(36), sa.ForeignKey("submissions.id"), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("media_type", sa.String(30), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("inspection", sa.JSON(), nullable=False),
    )
    op.create_index("ix_document_sources_submission_id", "document_sources", ["submission_id"])
    op.create_table(
        "document_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("submission_id", sa.String(36), sa.ForeignKey("submissions.id"), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("derivative_pdf", sa.LargeBinary(), nullable=False),
    )
    op.create_index("ix_document_runs_submission_id", "document_runs", ["submission_id"])
    op.create_table(
        "document_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("submission_id", sa.String(36), sa.ForeignKey("submissions.id"), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_document_events_submission_id", "document_events", ["submission_id"])
    op.create_table(
        "structured_inputs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("case_kind", sa.String(20), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
    )
    op.create_index("ix_structured_inputs_case_id", "structured_inputs", ["case_id"])

    op.create_table(
        "document_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("document_runs.id"), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
    )
    op.create_index("ix_document_reviews_run_id", "document_reviews", ["run_id"])


def downgrade():
    for name in [
        "document_reviews",
        "structured_inputs",
        "document_events",
        "document_runs",
        "document_sources",
        "submissions",
    ]:
        op.drop_table(name)
    op.drop_column("cases", "owner_id")
