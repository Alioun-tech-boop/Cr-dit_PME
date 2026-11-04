"""Version optimiste des dossiers pour refuser les écrasements périmés."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cases", sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1")
    )

    op.create_table(
        "security_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_id", sa.String(100), nullable=True),
        sa.Column("institution_id", sa.String(100), nullable=True),
        sa.Column("event", sa.String(120), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_security_events_institution_id", "security_events", ["institution_id"])


def downgrade():
    op.drop_table("security_events")
    op.drop_column("cases", "lock_version")
