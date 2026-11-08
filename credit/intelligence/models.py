"""Tables additives des niveaux décisionnel et institutionnel.

Aucune table existante n'est modifiée. Les analyses décisionnelles sont
immuables ; seules les métadonnées de publication client peuvent évoluer.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from credit.persistence import Base, identifier, now


class DecisionAnalysis(Base):
    __tablename__ = "decision_analyses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    case_kind: Mapped[str] = mapped_column(String(20))
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"), index=True)
    institution_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    engine_version: Mapped[str] = mapped_column(String(50))
    rules_version: Mapped[str] = mapped_column(String(50))
    input_sha256: Mapped[str] = mapped_column(String(64))
    report_sha256: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSON)
    client_visible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    published_note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Guarantee(Base):
    __tablename__ = "guarantees"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    case_kind: Mapped[str] = mapped_column(String(20))
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"), index=True)
    decision_analysis_id: Mapped[str] = mapped_column(
        ForeignKey("decision_analyses.id"), index=True
    )
    institution_id: Mapped[str] = mapped_column(String(100), index=True)
    partner_id: Mapped[str | None] = mapped_column(
        ForeignKey("bank_partners.id"), nullable=True, index=True
    )
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    borrower_name: Mapped[str] = mapped_column(String(200))
    borrower_type: Mapped[str] = mapped_column(String(30))
    sector: Mapped[str | None] = mapped_column(String(120), nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    requested_amount: Mapped[Decimal] = mapped_column(Numeric(24, 2))
    approved_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="XOF")
    status: Mapped[str] = mapped_column(String(30), default="proposed", index=True)
    risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    recommendation: Mapped[str | None] = mapped_column(String(40), nullable=True)
    conditions: Mapped[list] = mapped_column(JSON, default=list)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, onupdate=now
    )
    revision: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {"version_id_col": revision}


class GuaranteeEvent(Base):
    __tablename__ = "guarantee_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    guarantee_id: Mapped[str] = mapped_column(ForeignKey("guarantees.id"), index=True)
    action: Mapped[str] = mapped_column(String(40))
    actor_id: Mapped[str] = mapped_column(String(100))
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Claim(Base):
    __tablename__ = "guarantee_claims"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    guarantee_id: Mapped[str] = mapped_column(ForeignKey("guarantees.id"), index=True)
    institution_id: Mapped[str] = mapped_column(String(100), index=True)
    reference: Mapped[str] = mapped_column(String(100), unique=True)
    status: Mapped[str] = mapped_column(String(40), default="declared", index=True)
    declared_amount: Mapped[Decimal] = mapped_column(Numeric(24, 2))
    received_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 2), nullable=True)
    approved_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 2), nullable=True)
    paid_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 2), nullable=True)
    recovered_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="XOF")
    reason: Mapped[str] = mapped_column(String(2000))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, onupdate=now
    )
    revision: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {"version_id_col": revision}


class ClaimEvent(Base):
    __tablename__ = "claim_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    claim_id: Mapped[str] = mapped_column(ForeignKey("guarantee_claims.id"), index=True)
    action: Mapped[str] = mapped_column(String(40))
    actor_id: Mapped[str] = mapped_column(String(100))
    from_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_status: Mapped[str] = mapped_column(String(40))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 2), nullable=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class InstitutionCapacity(Base):
    __tablename__ = "institution_capacity"
    institution_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    as_of: Mapped[date] = mapped_column(Date)
    own_funds: Mapped[Decimal | None] = mapped_column(Numeric(24, 2), nullable=True)
    mobilizable_resources: Mapped[Decimal | None] = mapped_column(Numeric(24, 2), nullable=True)
    liquidities: Mapped[Decimal | None] = mapped_column(Numeric(24, 2), nullable=True)
    provisions: Mapped[Decimal | None] = mapped_column(Numeric(24, 2), nullable=True)
    safety_reserve: Mapped[Decimal | None] = mapped_column(Numeric(24, 2), nullable=True)
    max_global_exposure: Mapped[Decimal | None] = mapped_column(Numeric(24, 2), nullable=True)
    coverage_limit: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    max_sector_share: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    max_bank_share: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    max_borrower_share: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(300), nullable=True)
    updated_by: Mapped[str] = mapped_column(String(100))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, onupdate=now
    )
    revision: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {"version_id_col": revision}


class InstitutionLimit(Base):
    __tablename__ = "institution_limits"
    __table_args__ = (
        UniqueConstraint("institution_id", "scope", "key", name="uq_institution_limit_scope"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    institution_id: Mapped[str] = mapped_column(String(100), index=True)
    scope: Mapped[str] = mapped_column(String(20))
    key: Mapped[str] = mapped_column(String(120))
    max_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 2), nullable=True)
    max_share: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    updated_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, onupdate=now
    )
