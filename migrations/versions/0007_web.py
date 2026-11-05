"""Comptes navigateur provisionnés, sessions révocables et brouillons persistants."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "web_users",
        sa.Column("actor_id", sa.String(100), primary_key=True),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(300), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    op.create_table(
        "web_sessions",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("actor_id", sa.String(100), sa.ForeignKey("web_users.actor_id"), nullable=False),
        sa.Column("csrf", sa.String(100), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_web_sessions_actor_id", "web_sessions", ["actor_id"])
    op.create_table(
        "journey_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(100), nullable=False),
        sa.Column("institution_id", sa.String(100), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=True),
        sa.Column("operation_key", sa.String(128), nullable=False, unique=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_journey_drafts_owner_id", "journey_drafts", ["owner_id"])


def downgrade():
    op.drop_table("journey_drafts")
    op.drop_table("web_sessions")
    op.drop_table("web_users")
