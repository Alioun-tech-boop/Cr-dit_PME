from datetime import date, datetime, timezone
from typing import Literal

from pydantic import Field, field_validator

from credit.shared.contracts import Contract


class DocumentMetadata(Contract):
    id: str
    case_id: str
    case_kind: Literal["individuals", "businesses"]
    document_type: str
    role: str
    period: date
    document_sha256: str
    created_at: datetime
    status: Literal["extracted_unverified"] = "extracted_unverified"
    ready_for_scoring: Literal[False] = False

    @field_validator("created_at")
    @classmethod
    def utc_timestamp(cls, value):
        # SQLite ne restitue pas les fuseaux ; les dates persistées sont en UTC.
        return (
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None
            else value.astimezone(timezone.utc)
        )


class DocumentResult(DocumentMetadata):
    extraction: dict = Field(
        description="Résultat brut non vérifié ; sources et avertissements intacts"
    )
