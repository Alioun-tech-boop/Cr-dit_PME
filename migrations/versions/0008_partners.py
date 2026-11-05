"""Revue interne, attestations, paquet privé et outbox bancaire."""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "case_grants",
        sa.Column(
            "case_id",
            sa.String(length=36),
            sa.ForeignKey("cases.id"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("actor_id", sa.String(length=100), primary_key=True, nullable=False),
        sa.Column("granted_by", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "institution_workflow_policies",
        sa.Column("institution_id", sa.String(length=100), primary_key=True, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
    )
    op.create_table(
        "bank_partners",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("issuer_id", sa.String(length=100), nullable=False),
        sa.Column("bank_institution_id", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_bank_partners_bank_institution_id",
        "bank_partners",
        ["bank_institution_id"],
        unique=False,
    )
    op.create_index("ix_bank_partners_issuer_id", "bank_partners", ["issuer_id"], unique=False)
    op.create_table(
        "internal_reviews",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("case_id", sa.String(length=36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column(
            "assessment_id", sa.String(length=36), sa.ForeignKey("assessments.id"), nullable=False
        ),
        sa.Column("case_version", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("operation_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.UniqueConstraint("case_id", "operation_key", name="uq_review_operation"),
    )
    op.create_index("ix_internal_reviews_case_id", "internal_reviews", ["case_id"], unique=False)
    op.create_table(
        "partner_packet_files",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "review_id", sa.String(length=36), sa.ForeignKey("internal_reviews.id"), nullable=False
        ),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("media_type", sa.String(length=60), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_partner_packet_files_review_id", "partner_packet_files", ["review_id"], unique=False
    )
    op.create_table(
        "internal_attestations",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("public_token", sa.String(length=100), nullable=False, unique=True),
        sa.Column(
            "review_id", sa.String(length=36), sa.ForeignKey("internal_reviews.id"), nullable=False
        ),
        sa.Column("key_id", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.UniqueConstraint("review_id", name="uq_attestation_review"),
    )
    op.create_index(
        "ix_internal_attestations_review_id", "internal_attestations", ["review_id"], unique=False
    )
    op.create_table(
        "bank_transmissions",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("case_id", sa.String(length=36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column(
            "review_id", sa.String(length=36), sa.ForeignKey("internal_reviews.id"), nullable=False
        ),
        sa.Column(
            "attestation_id",
            sa.String(length=36),
            sa.ForeignKey("internal_attestations.id"),
            nullable=False,
        ),
        sa.Column(
            "partner_id", sa.String(length=36), sa.ForeignKey("bank_partners.id"), nullable=False
        ),
        sa.Column("issuer_id", sa.String(length=100), nullable=False),
        sa.Column("bank_institution_id", sa.String(length=100), nullable=False),
        sa.Column("applicant_id", sa.String(length=100), nullable=False),
        sa.Column("operation_key", sa.String(length=128), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.UniqueConstraint("case_id", "operation_key", name="uq_transmission_operation"),
    )
    op.create_index(
        "ix_bank_transmissions_applicant_id", "bank_transmissions", ["applicant_id"], unique=False
    )
    op.create_index(
        "ix_bank_transmissions_bank_institution_id",
        "bank_transmissions",
        ["bank_institution_id"],
        unique=False,
    )
    op.create_index(
        "ix_bank_transmissions_case_id", "bank_transmissions", ["case_id"], unique=False
    )
    op.create_index(
        "ix_bank_transmissions_issuer_id", "bank_transmissions", ["issuer_id"], unique=False
    )
    op.create_table(
        "partner_outbox",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "transmission_id",
            sa.String(length=36),
            sa.ForeignKey("bank_transmissions.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("state", sa.String(length=30), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
    )
    op.create_index("ix_partner_outbox_due_at", "partner_outbox", ["due_at"], unique=False)
    op.create_table(
        "partner_events",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "transmission_id",
            sa.String(length=36),
            sa.ForeignKey("bank_transmissions.id"),
            nullable=True,
        ),
        sa.Column("actor_id", sa.String(length=100), nullable=False),
        sa.Column("institution_id", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("event_key", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.UniqueConstraint("transmission_id", "event_key", name="uq_bank_event"),
    )
    op.create_index(
        "ix_partner_events_transmission_id", "partner_events", ["transmission_id"], unique=False
    )
    op.create_table(
        "bank_attachments",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "transmission_id",
            sa.String(length=36),
            sa.ForeignKey("bank_transmissions.id"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("media_type", sa.String(length=60), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_bank_attachments_transmission_id", "bank_attachments", ["transmission_id"], unique=False
    )


def downgrade():
    op.drop_index("ix_bank_attachments_transmission_id", table_name="bank_attachments")
    op.drop_table("bank_attachments")
    op.drop_index("ix_partner_events_transmission_id", table_name="partner_events")
    op.drop_table("partner_events")
    op.drop_index("ix_partner_outbox_due_at", table_name="partner_outbox")
    op.drop_table("partner_outbox")
    op.drop_index("ix_bank_transmissions_applicant_id", table_name="bank_transmissions")
    op.drop_index("ix_bank_transmissions_bank_institution_id", table_name="bank_transmissions")
    op.drop_index("ix_bank_transmissions_case_id", table_name="bank_transmissions")
    op.drop_index("ix_bank_transmissions_issuer_id", table_name="bank_transmissions")
    op.drop_table("bank_transmissions")
    op.drop_index("ix_internal_attestations_review_id", table_name="internal_attestations")
    op.drop_table("internal_attestations")
    op.drop_index("ix_partner_packet_files_review_id", table_name="partner_packet_files")
    op.drop_table("partner_packet_files")
    op.drop_index("ix_internal_reviews_case_id", table_name="internal_reviews")
    op.drop_table("internal_reviews")
    op.drop_index("ix_bank_partners_bank_institution_id", table_name="bank_partners")
    op.drop_index("ix_bank_partners_issuer_id", table_name="bank_partners")
    op.drop_table("bank_partners")
    op.drop_table("institution_workflow_policies")
    op.drop_table("case_grants")
