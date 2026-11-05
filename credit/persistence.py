from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    Integer,
    create_engine,
    UniqueConstraint,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from credit.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


def identifier():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc)


class CaseRecord(Base):
    __tablename__ = "cases"
    lock_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    __mapper_args__ = {"version_id_col": lock_version}
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    kind: Mapped[str] = mapped_column(String(20))
    institution_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    owner_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class AnalysisRecord(Base):
    __tablename__ = "analyses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    input_snapshot: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    scenario: Mapped[dict] = mapped_column(JSON)
    engine_version: Mapped[str] = mapped_column(String(50))
    configuration: Mapped[dict] = mapped_column(JSON)
    evidence_snapshot: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DocumentRecord(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    case_kind: Mapped[str] = mapped_column(String(20))
    document_type: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(120))
    period: Mapped[date] = mapped_column(Date)
    document_sha256: Mapped[str] = mapped_column(String(64))
    original_pdf: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    extraction: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


def sessions(url=DATABASE_URL):
    engine = create_engine(url)
    return engine, sessionmaker(engine, expire_on_commit=False)


class SubmissionRecord(Base):
    __tablename__ = "submissions"
    lock_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    __mapper_args__ = {"version_id_col": lock_version}
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    case_kind: Mapped[str] = mapped_column(String(20))
    data: Mapped[dict] = mapped_column(JSON)


class SourceRecord(Base):
    __tablename__ = "document_sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), index=True)
    sha256: Mapped[str] = mapped_column(String(64))
    media_type: Mapped[str] = mapped_column(String(30))
    payload: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    inspection: Mapped[dict] = mapped_column(JSON)


class DocumentRun(Base):
    __tablename__ = "document_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), index=True)
    data: Mapped[dict] = mapped_column(JSON)
    derivative_pdf: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)


class DocumentEvent(Base):
    __tablename__ = "document_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), index=True)
    actor_id: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class StructuredRecord(Base):
    __tablename__ = "structured_inputs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    case_kind: Mapped[str] = mapped_column(String(20))
    data: Mapped[dict] = mapped_column(JSON)


class ReviewRecord(Base):
    __tablename__ = "document_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    run_id: Mapped[str] = mapped_column(ForeignKey("document_runs.id"), index=True)
    actor_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    data: Mapped[dict] = mapped_column(JSON)


class AssessmentRecord(Base):
    __tablename__ = "assessments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    case_kind: Mapped[str] = mapped_column(String(20))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("assessments.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    data: Mapped[dict] = mapped_column(JSON)


class PrintEdition(Base):
    __tablename__ = "print_editions"
    __table_args__ = (
        UniqueConstraint("case_id", "template_id", "audience", "version", name="uq_print_version"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    case_kind: Mapped[str] = mapped_column(String(20))
    template_id: Mapped[str] = mapped_column(String(60))
    audience: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer)
    assessment_id: Mapped[str | None] = mapped_column(ForeignKey("assessments.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    author_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    data: Mapped[dict] = mapped_column(JSON)
    html_content: Mapped[str | None] = mapped_column(Text, nullable=True, deferred=True)
    pdf_content: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)


class PrintEvent(Base):
    __tablename__ = "print_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    edition_id: Mapped[str] = mapped_column(ForeignKey("print_editions.id"), index=True)
    actor_id: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PrintPublication(Base):
    __tablename__ = "print_publications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"), index=True)
    actor_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    data: Mapped[dict] = mapped_column(JSON)


class SecurityEvent(Base):
    __tablename__ = "security_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    actor_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    institution_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    event: Mapped[str] = mapped_column(String(120))
    outcome: Mapped[str] = mapped_column(String(20))
    request_id: Mapped[str] = mapped_column(String(36))
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WebUser(Base):
    __tablename__ = "web_users"
    actor_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {"version_id_col": revision}


class WebRegistration(Base):
    __tablename__ = "web_registrations"
    actor_id: Mapped[str] = mapped_column(ForeignKey("web_users.actor_id"), primary_key=True)
    institution_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    identifier: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    channel: Mapped[str] = mapped_column(String(10), nullable=False)
    contact_status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WebSession(Base):
    __tablename__ = "web_sessions"
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("web_users.actor_id"), index=True)
    csrf: Mapped[str] = mapped_column(String(100))
    fingerprint: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class JourneyDraft(Base):
    __tablename__ = "journey_drafts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    owner_id: Mapped[str] = mapped_column(String(100), index=True)
    institution_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON)
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id"), nullable=True)
    operation_key: Mapped[str] = mapped_column(String(128), unique=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {"version_id_col": version}
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


# Chargement des tables du parcours partenaire pour Alembic et les bases de test.
from credit.partners import models as partner_models  # noqa: E402, F401
