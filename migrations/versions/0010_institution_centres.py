"""Comptes partenaires, décisions bancaires immuables et boîte de réception client."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "institution_accounts",
        sa.Column(
            "actor_id", sa.String(100), sa.ForeignKey("web_users.actor_id"), primary_key=True
        ),
        sa.Column("partner_id", sa.String(36), sa.ForeignKey("bank_partners.id"), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("professional_name", sa.String(150), nullable=False),
        sa.Column("function", sa.String(150), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("invitation_digest", sa.String(64), nullable=True, unique=True),
        sa.Column("invitation_expires", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_institution_accounts_partner_id", "institution_accounts", ["partner_id"])
    op.create_table(
        "bank_decision_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "transmission_id",
            sa.String(36),
            sa.ForeignKey("bank_transmissions.id"),
            unique=True,
            nullable=False,
        ),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("bank_institution_id", sa.String(100), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("operation_key", sa.String(128), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("public_token", sa.String(100), nullable=True, unique=True),
        sa.Column("payload", sa.LargeBinary(), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_bank_decision_records_bank_institution_id",
        "bank_decision_records",
        ["bank_institution_id"],
    )
    op.create_table(
        "client_inbox_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("institution_id", sa.String(100), nullable=False),
        sa.Column(
            "transmission_id", sa.String(36), sa.ForeignKey("bank_transmissions.id"), nullable=False
        ),
        sa.Column(
            "decision_id", sa.String(36), sa.ForeignKey("bank_decision_records.id"), nullable=False
        ),
        sa.Column("event_key", sa.String(100), unique=True, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_client_inbox_messages_actor_id", "client_inbox_messages", ["actor_id"])
    op.create_index(
        "ix_client_inbox_messages_institution_id", "client_inbox_messages", ["institution_id"]
    )


def downgrade():
    op.drop_table("client_inbox_messages")
    op.drop_table("bank_decision_records")
    op.drop_table("institution_accounts")
