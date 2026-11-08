"""Analyses décisionnelles, garanties, sinistres et capacité institutionnelle.

Migration additive : aucune table existante n'est modifiée.
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "decision_analyses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("case_kind", sa.String(20), nullable=False),
        sa.Column(
            "assessment_id", sa.String(36), sa.ForeignKey("assessments.id"), nullable=False
        ),
        sa.Column("institution_id", sa.String(100), nullable=True),
        sa.Column("engine_version", sa.String(50), nullable=False),
        sa.Column("rules_version", sa.String(50), nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("report_sha256", sa.String(64), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("client_visible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.String(100), nullable=True),
        sa.Column("published_note", sa.String(2000), nullable=True),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_decision_analyses_case_id", "decision_analyses", ["case_id"])
    op.create_index(
        "ix_decision_analyses_assessment_id", "decision_analyses", ["assessment_id"]
    )
    op.create_index(
        "ix_decision_analyses_institution_id", "decision_analyses", ["institution_id"]
    )

    op.create_table(
        "guarantees",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("case_kind", sa.String(20), nullable=False),
        sa.Column(
            "assessment_id", sa.String(36), sa.ForeignKey("assessments.id"), nullable=False
        ),
        sa.Column(
            "decision_analysis_id",
            sa.String(36),
            sa.ForeignKey("decision_analyses.id"),
            nullable=False,
        ),
        sa.Column("institution_id", sa.String(100), nullable=False),
        sa.Column(
            "partner_id", sa.String(36), sa.ForeignKey("bank_partners.id"), nullable=True
        ),
        sa.Column("reference", sa.String(100), nullable=True, unique=True),
        sa.Column("borrower_name", sa.String(200), nullable=False),
        sa.Column("borrower_type", sa.String(30), nullable=False),
        sa.Column("sector", sa.String(120), nullable=True),
        sa.Column("region", sa.String(120), nullable=True),
        sa.Column("requested_amount", sa.Numeric(24, 2), nullable=False),
        sa.Column("approved_amount", sa.Numeric(24, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=True),
        sa.Column("recommendation", sa.String(40), nullable=True),
        sa.Column("conditions", sa.JSON(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    op.create_index("ix_guarantees_case_id", "guarantees", ["case_id"])
    op.create_index("ix_guarantees_assessment_id", "guarantees", ["assessment_id"])
    op.create_index(
        "ix_guarantees_decision_analysis_id", "guarantees", ["decision_analysis_id"]
    )
    op.create_index("ix_guarantees_institution_id", "guarantees", ["institution_id"])
    op.create_index("ix_guarantees_partner_id", "guarantees", ["partner_id"])
    op.create_index("ix_guarantees_status", "guarantees", ["status"])

    op.create_table(
        "guarantee_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "guarantee_id", sa.String(36), sa.ForeignKey("guarantees.id"), nullable=False
        ),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("from_status", sa.String(30), nullable=True),
        sa.Column("to_status", sa.String(30), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_guarantee_events_guarantee_id", "guarantee_events", ["guarantee_id"]
    )

    op.create_table(
        "guarantee_claims",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "guarantee_id", sa.String(36), sa.ForeignKey("guarantees.id"), nullable=False
        ),
        sa.Column("institution_id", sa.String(100), nullable=False),
        sa.Column("reference", sa.String(100), nullable=False, unique=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("declared_amount", sa.Numeric(24, 2), nullable=False),
        sa.Column("received_amount", sa.Numeric(24, 2), nullable=True),
        sa.Column("approved_amount", sa.Numeric(24, 2), nullable=True),
        sa.Column("paid_amount", sa.Numeric(24, 2), nullable=True),
        sa.Column("recovered_amount", sa.Numeric(24, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_guarantee_claims_guarantee_id", "guarantee_claims", ["guarantee_id"]
    )
    op.create_index(
        "ix_guarantee_claims_institution_id", "guarantee_claims", ["institution_id"]
    )
    op.create_index("ix_guarantee_claims_status", "guarantee_claims", ["status"])

    op.create_table(
        "claim_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "claim_id",
            sa.String(36),
            sa.ForeignKey("guarantee_claims.id"),
            nullable=False,
        ),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("from_status", sa.String(40), nullable=True),
        sa.Column("to_status", sa.String(40), nullable=False),
        sa.Column("amount", sa.Numeric(24, 2), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_claim_events_claim_id", "claim_events", ["claim_id"])

    op.create_table(
        "institution_capacity",
        sa.Column("institution_id", sa.String(100), primary_key=True),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("own_funds", sa.Numeric(24, 2), nullable=True),
        sa.Column("mobilizable_resources", sa.Numeric(24, 2), nullable=True),
        sa.Column("liquidities", sa.Numeric(24, 2), nullable=True),
        sa.Column("provisions", sa.Numeric(24, 2), nullable=True),
        sa.Column("safety_reserve", sa.Numeric(24, 2), nullable=True),
        sa.Column("max_global_exposure", sa.Numeric(24, 2), nullable=True),
        sa.Column("coverage_limit", sa.Numeric(12, 6), nullable=True),
        sa.Column("max_sector_share", sa.Numeric(12, 6), nullable=True),
        sa.Column("max_bank_share", sa.Numeric(12, 6), nullable=True),
        sa.Column("max_borrower_share", sa.Numeric(12, 6), nullable=True),
        sa.Column("source_reference", sa.String(300), nullable=True),
        sa.Column("updated_by", sa.String(100), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
    )

    op.create_table(
        "institution_limits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("institution_id", sa.String(100), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("max_amount", sa.Numeric(24, 2), nullable=True),
        sa.Column("max_share", sa.Numeric(12, 6), nullable=True),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.Column("updated_by", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "institution_id", "scope", "key", name="uq_institution_limit_scope"
        ),
    )
    op.create_index(
        "ix_institution_limits_institution_id", "institution_limits", ["institution_id"]
    )


def downgrade():
    op.drop_table("institution_limits")
    op.drop_table("institution_capacity")
    op.drop_table("claim_events")
    op.drop_table("guarantee_claims")
    op.drop_table("guarantee_events")
    op.drop_table("guarantees")
    op.drop_table("decision_analyses")
