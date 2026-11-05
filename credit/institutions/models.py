from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, DateTime, JSON, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column
from credit.persistence import Base, identifier, now


class InstitutionAccount(Base):
    __tablename__ = "institution_accounts"
    actor_id: Mapped[str] = mapped_column(ForeignKey("web_users.actor_id"), primary_key=True)
    partner_id: Mapped[str] = mapped_column(ForeignKey("bank_partners.id"), index=True)
    role: Mapped[str] = mapped_column(String(30))
    professional_name: Mapped[str] = mapped_column(String(150))
    function: Mapped[str] = mapped_column(String(150))
    status: Mapped[str] = mapped_column(String(20), default="invited")
    invitation_digest: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    invitation_expires: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revision: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {"version_id_col": revision}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class BankDecisionRecord(Base):
    __tablename__ = "bank_decision_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    transmission_id: Mapped[str] = mapped_column(ForeignKey("bank_transmissions.id"), unique=True)
    actor_id: Mapped[str] = mapped_column(String(100))
    bank_institution_id: Mapped[str] = mapped_column(String(100), index=True)
    decision: Mapped[str] = mapped_column(String(20))
    state: Mapped[str] = mapped_column(String(30))
    operation_key: Mapped[str] = mapped_column(String(128))
    request_sha256: Mapped[str] = mapped_column(String(64))
    public_token: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    payload: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ClientMessage(Base):
    __tablename__ = "client_inbox_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    actor_id: Mapped[str] = mapped_column(String(100), index=True)
    institution_id: Mapped[str] = mapped_column(String(100), index=True)
    transmission_id: Mapped[str] = mapped_column(ForeignKey("bank_transmissions.id"))
    decision_id: Mapped[str] = mapped_column(ForeignKey("bank_decision_records.id"))
    event_key: Mapped[str] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
