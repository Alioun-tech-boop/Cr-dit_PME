from sqlalchemy import String, Integer, ForeignKey, JSON, DateTime, LargeBinary, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from credit.persistence import Base, identifier, now
from datetime import datetime


class CaseGrant(Base):
    __tablename__ = "case_grants"
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    granted_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class InstitutionPolicy(Base):
    __tablename__ = "institution_workflow_policies"
    institution_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {"version_id_col": version}
    data: Mapped[dict] = mapped_column(JSON)


class Partner(Base):
    __tablename__ = "bank_partners"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    issuer_id: Mapped[str] = mapped_column(String(100), index=True)
    bank_institution_id: Mapped[str] = mapped_column(String(100), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {"version_id_col": version}
    status: Mapped[str] = mapped_column(String(30), default="preparation")
    data: Mapped[dict] = mapped_column(JSON)


class InternalReview(Base):
    __tablename__ = "internal_reviews"
    __table_args__ = (UniqueConstraint("case_id", "operation_key", name="uq_review_operation"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"))
    case_version: Mapped[int] = mapped_column(Integer)
    fingerprint: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(30), default="internal_review")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {"version_id_col": revision}
    operation_key: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    data: Mapped[dict] = mapped_column(JSON)


class PacketFile(Base):
    __tablename__ = "partner_packet_files"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    review_id: Mapped[str] = mapped_column(ForeignKey("internal_reviews.id"), index=True)
    category: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(150))
    media_type: Mapped[str] = mapped_column(String(60))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    payload: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    metadata_json: Mapped[dict] = mapped_column(JSON)


class Attestation(Base):
    __tablename__ = "internal_attestations"
    __table_args__ = (UniqueConstraint("review_id", name="uq_attestation_review"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    public_token: Mapped[str] = mapped_column(String(100), unique=True)
    review_id: Mapped[str] = mapped_column(ForeignKey("internal_reviews.id"), index=True)
    key_id: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(30), default="valid")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data: Mapped[dict] = mapped_column(JSON)


class Transmission(Base):
    __tablename__ = "bank_transmissions"
    __table_args__ = (
        UniqueConstraint("case_id", "operation_key", name="uq_transmission_operation"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    review_id: Mapped[str] = mapped_column(ForeignKey("internal_reviews.id"))
    attestation_id: Mapped[str] = mapped_column(ForeignKey("internal_attestations.id"))
    partner_id: Mapped[str] = mapped_column(ForeignKey("bank_partners.id"))
    issuer_id: Mapped[str] = mapped_column(String(100), index=True)
    bank_institution_id: Mapped[str] = mapped_column(String(100), index=True)
    applicant_id: Mapped[str] = mapped_column(String(100), index=True)
    operation_key: Mapped[str] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(40), default="ready")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {"version_id_col": revision}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    data: Mapped[dict] = mapped_column(JSON)


class Outbox(Base):
    __tablename__ = "partner_outbox"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    transmission_id: Mapped[str] = mapped_column(ForeignKey("bank_transmissions.id"), unique=True)
    state: Mapped[str] = mapped_column(String(30), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {"version_id_col": revision}
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    leased_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data: Mapped[dict] = mapped_column(JSON)


class PartnerEvent(Base):
    __tablename__ = "partner_events"
    __table_args__ = (UniqueConstraint("transmission_id", "event_key", name="uq_bank_event"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    transmission_id: Mapped[str | None] = mapped_column(
        ForeignKey("bank_transmissions.id"), nullable=True, index=True
    )
    actor_id: Mapped[str] = mapped_column(String(100))
    institution_id: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(60))
    event_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    data: Mapped[dict] = mapped_column(JSON)


class BankAttachment(Base):
    __tablename__ = "bank_attachments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    transmission_id: Mapped[str] = mapped_column(ForeignKey("bank_transmissions.id"), index=True)
    actor_id: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(50))
    sha256: Mapped[str] = mapped_column(String(64))
    media_type: Mapped[str] = mapped_column(String(60))
    payload: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
