from datetime import date
from typing import Literal
from pydantic import Field, model_validator
from credit.shared.contracts import Contract

BASE_CATEGORIES = {
    "identification",
    "credit_request",
    "declaration",
    "budget",
    "debts",
    "lender_report",
    "analysis_summary",
    "inventory",
    "attestation",
}


class Professional(Contract):
    actor_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=150)
    function: str = Field(min_length=1, max_length=150)


class WorkflowPolicy(Contract):
    issuer_name: str = Field(min_length=1, max_length=200)
    issuer_identity_statement: str = Field(min_length=5, max_length=2000)
    scope: str = Field(min_length=10, max_length=3000)
    demonstration: bool = False
    signatories: list[Professional] = Field(min_length=1, max_length=20)
    reviewers: list[str] = Field(default_factory=list, max_length=30)
    required_approvals: int = Field(default=1, ge=1, le=3)
    separate_analysis_author: bool = True
    allow_incomplete_with_reserves: bool = False
    allow_deficits_with_reserves: bool = False
    require_approved_financial_policy: bool = True
    require_business_authority_evidence: bool = True
    attestation_valid_days: int | None = Field(default=30, ge=1, le=365)
    consent_valid_hours: int = Field(default=72, ge=1, le=720)
    approved_reference: str = Field(min_length=5, max_length=500)
    legal_review_reference: str = Field(min_length=5, max_length=500)

    @model_validator(mode="after")
    def unique_signers(self):
        if (
            len({s.actor_id for s in self.signatories}) != len(self.signatories)
            or len(self.signatories) < self.required_approvals
        ):
            raise ValueError("Signataires distincts en nombre suffisant requis")
        return self


class PartnerInput(Contract):
    institution_type: Literal["bank", "microfinance"] = "bank"
    bank_institution_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=3, max_length=200)
    presentation: str = Field(min_length=5, max_length=3000)
    country: str = Field(default="BF", min_length=2, max_length=2)
    activity_scope: str = Field(min_length=3, max_length=1000)
    cores: list[Literal["individuals", "businesses"]] = Field(min_length=1)
    profiles: list[str] = Field(min_length=1, max_length=10)
    products: list[str] = Field(min_length=1, max_length=20)
    required_categories: list[str] = Field(
        default_factory=lambda: [
            "identification",
            "credit_request",
            "lender_report",
            "analysis_summary",
            "attestation",
        ]
    )
    allowed_categories: list[str] = Field(default_factory=lambda: sorted(BASE_CATEGORIES))
    reception_mode: Literal["portal", "api_demo"] = "portal"
    demonstration: bool = False
    information_updated_on: date
    provided_conditions: str | None = Field(default=None, max_length=2000)
    processing_notice: str = Field(min_length=10, max_length=3000)
    webhook_secret_env: str | None = Field(
        default=None, pattern=r"^CREDIT_PARTNER_WEBHOOK_[A-Z0-9_]{1,50}$"
    )
    demo_failures: int = Field(default=0, ge=0, le=3)

    @model_validator(mode="after")
    def coherence(self):
        if self.reception_mode == "api_demo" and not self.demonstration:
            raise ValueError("Connecteur simulé réservé à la démonstration")
        if not set(self.required_categories) <= set(self.allowed_categories):
            raise ValueError("Pièces exigées hors du périmètre autorisé")
        return self


class PartnerActivation(Contract):
    agreement_reference: str = Field(min_length=5, max_length=500)
    representative_verification_reference: str = Field(min_length=5, max_length=500)
    data_sharing_reference: str = Field(min_length=5, max_length=500)
    legal_review_reference: str = Field(min_length=5, max_length=500)
    expected_version: int = Field(ge=1)


class PartnerStatus(Contract):
    status: Literal["unavailable", "suspended", "preparation"]
    reason: str = Field(min_length=5, max_length=1000)
    expected_version: int = Field(ge=1)


class StartReview(Contract):
    assessment_id: str
    expected_case_version: int = Field(ge=1)
    source_ids: list[str] = Field(default_factory=list, max_length=20)
    business_authority_source_id: str | None = None


class ReviewDecision(Contract):
    decision: Literal["approve", "not_approved", "needs_completion"]
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=10, max_length=3000)
    public_reserves: str = Field(default="", max_length=3000)
    authorize_packet_preview: bool = Field(default=False, strict=True)


class SelectPartner(Contract):
    partner_id: str
    review_id: str
    file_ids: list[str] = Field(min_length=1, max_length=40)


class Confirm(Contract):
    expected_revision: int = Field(ge=1)
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    attestation_id: str
    consent_version: Literal["bank-sharing-fr-v1"]
    accepted: bool = Field(strict=True)
    authority_statement: str = Field(min_length=10, max_length=2000)


class BankAction(Contract):
    expected_revision: int = Field(ge=1)
    action: Literal["received", "under_review", "additional_information", "decision"]
    reason: str = Field(min_length=5, max_length=3000)
    requested_information: list[str] = Field(default_factory=list, max_length=30)
    decision: (
        Literal[
            "favorable_opinion",
            "conditional_offer",
            "formal_offer",
            "refused",
            "disbursement_confirmed",
        ]
        | None
    ) = None
    external_reference: str | None = Field(default=None, max_length=200)
    attachment_ids: list[str] = Field(default_factory=list, max_length=10)


class ApplicantSupplement(Contract):
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=5, max_length=2000)
    attachment_ids: list[str] = Field(min_length=1, max_length=10)
    accepted: bool = Field(strict=True)


class Reason(Contract):
    reason: str = Field(min_length=5, max_length=2000)


class Webhook(Contract):
    event_id: str = Field(min_length=1, max_length=100)
    transmission_id: str
    sequence: int = Field(ge=1)
    event: BankAction


class AssignApplicant(Contract):
    actor_id: str = Field(min_length=1, max_length=100)
    expected_case_version: int = Field(ge=1)
