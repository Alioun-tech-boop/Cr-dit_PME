from datetime import date
from typing import Literal

from pydantic import Field, JsonValue, model_validator, field_validator
from credit.shared.contracts import Contract


class NewSubmission(Contract):
    document_type: str = Field(min_length=1, max_length=100)
    role: str = Field(min_length=1, max_length=120)
    period: date

    @field_validator("role", "exception_reason", mode="before")
    @classmethod
    def strip_reason(cls, value):
        return value.strip() if isinstance(value, str) else value

    supporting_structured_id: str | None = None
    exception_reason: str | None = Field(default=None, min_length=10, max_length=2000)


class PageEdit(Contract):
    id: str
    rotation: Literal[0, 90, 180, 270] = 0
    crop: tuple[float, float, float, float] = (0, 0, 1, 1)

    @model_validator(mode="after")
    def valid_crop(self):
        x0, y0, x1, y1 = self.crop
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1) or x1 - x0 < 0.02 or y1 - y0 < 0.02:
            raise ValueError("Recadrage normalisé invalide ou trop petit")
        return self


class EditPages(Contract):
    expected_revision: int = Field(ge=1)
    pages: list[PageEdit] = Field(max_length=100)


class ManualRegion(Contract):
    id: str = Field(pattern=r"^manual:[a-zA-Z0-9_-]{1,64}$")
    page_id: str
    bbox: tuple[float, float, float, float]


class ReviewInput(Contract):
    decisions: dict[str, JsonValue]
    regions: list[ManualRegion] = Field(default_factory=list, max_length=100)


class StructuredInput(Contract):
    document_type: str
    period: date
    fields: dict[str, JsonValue] = Field(min_length=1)
