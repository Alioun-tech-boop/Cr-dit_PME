"""Contrats de présentation : aucun calcul financier dans les moteurs de rendu."""

from typing import Literal
from pydantic import Field
from credit.shared.contracts import Contract

Audience = Literal["applicant", "analyst"]


class Table(Contract):
    columns: list[str]
    rows: list[list[str]]


class Section(Contract):
    title: str
    paragraphs: list[str] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)


class Presentation(Contract):
    schema_version: str = "credit-pme.print.v1"
    template_version: str = "print-1.0.0"
    template_id: str
    title: str
    audience: Audience
    status: str
    metadata: dict[str, str]
    missing_information: list[str]
    notices: list[str]
    sections: list[Section]
    platform_name: str = "Crédit PME"
    logo_png: str | None = None
    signatures: bool = False


class PrintRequest(Contract):
    template_id: str = Field(pattern=r"^[a-z_]+$")
    audience: Audience = "applicant"
    assessment_id: str | None = None
    language: Literal["fr"] = "fr"
    generate_now: bool = True


class Publication(Contract):
    # Pas de publication automatique de sources, règles, scores ou observations internes.
    financial_results: bool = False
    suggestions: bool = False
    justification: str = Field(min_length=5, max_length=1000)


class ReturnedDocument(Contract):
    submission_id: str
    description: str = Field(min_length=3, max_length=500)
