"""Comptes demandeurs créés par e-mail ou téléphone ; périmètre institutionnel serveur."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "web_registrations",
        sa.Column(
            "actor_id", sa.String(100), sa.ForeignKey("web_users.actor_id"), primary_key=True
        ),
        sa.Column("institution_id", sa.String(100), nullable=False),
        sa.Column("identifier", sa.String(100), nullable=False, unique=True),
        sa.Column("channel", sa.String(10), nullable=False),
        sa.Column("contact_status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_web_registrations_institution_id", "web_registrations", ["institution_id"])


def downgrade():
    op.drop_index("ix_web_registrations_institution_id", table_name="web_registrations")
    op.drop_table("web_registrations")
