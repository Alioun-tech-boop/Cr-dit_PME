"""Champs descriptifs facultatifs ; ne modifient aucun calcul de crédit."""

from pydantic import Field
from credit.shared.contracts import Contract


class Representative(Contract):
    name: str = Field(max_length=300)
    role: str = Field(max_length=300)
    authority_reference: str | None = Field(default=None, max_length=500)


class RecordDetails(Contract):
    address: str | None = Field(default=None, max_length=2000)
    telephone: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=300)
    identity_reference: str | None = Field(default=None, max_length=300)
    legal_form: str | None = Field(default=None, max_length=200)
    rccm: str | None = Field(default=None, max_length=300)
    ifu: str | None = Field(default=None, max_length=300)
    representatives: list[Representative] = Field(default_factory=list, max_length=30)
    applicant_comments: str | None = Field(default=None, max_length=10000)
    internal_observations: str | None = Field(default=None, max_length=10000)
