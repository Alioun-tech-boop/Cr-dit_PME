from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field
from credit.shared.contracts import Contract

Status = Literal["favorable", "vigilance", "defavorable", "incomplet", "non_applicable"]


class DataUse(Contract):
    path: str
    value: Any
    state: str = "declared"
    period: date | None = None
    basis: str | None = None
    unit: str | None = None
    sources: list[dict] = Field(default_factory=list)


class Indicator(Contract):
    id: str
    value: Decimal | None
    unit: str
    formula: str
    period: date | None = None
    input_paths: list[str] = Field(default_factory=list)
    unavailable_reason: str | None = None


class RuleResult(Contract):
    id: str
    version: str = "financial-facts-1"
    indicator_id: str
    operator: str
    threshold: Decimal | None = None
    observed: Decimal | None = None
    passed: bool | None
    explanation: str
    validation_status: str = "mathematical_fact"


class SectionResult(Contract):
    id: str
    title: str
    status: Status = "favorable"
    purpose: Literal["financial", "documentary", "collateral"] = "financial"
    periods: list[date] = Field(default_factory=list)
    data_used: list[DataUse] = Field(default_factory=list)
    indicators: list[Indicator] = Field(default_factory=list)
    rules: list[RuleResult] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    alerts: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    explanation: str = ""
    suggestion_ids: list[str] = Field(default_factory=list)
    score: Decimal | None = None
    score_validation_status: str = "not_available"


class Suggestion(Contract):
    id: str
    section_id: str
    problem: str
    triggers: list[str]
    action: str
    recipient: Literal["demandeur", "analyste", "preteur"]
    priority: Literal["haute", "moyenne", "basse"]
    prerequisites: list[str]
    simulated_effect: dict | None = None
    costs_and_limits: list[str]
    evidence_needed: list[str]


class AssessmentReport(Contract):
    schema_version: str = "credit-pme.assessment.v1"
    engine_version: str
    core: Literal["individuals", "businesses"]
    operating_state: str
    operating_states: list[str]
    summary: str
    sections: list[SectionResult]
    major_alerts: list[str]
    missing_information: list[str]
    financial_risk: dict
    documentary_quality: dict
    scoring: dict
    suggestions: list[Suggestion]
    comparisons: list[dict] = Field(default_factory=list)
    financing_conditions: dict
    financial_calculations: dict
    assumptions: list[str]
    sources: list[dict]
    versions: dict
    policy_snapshot: dict | None
    human_validations: list[dict] = Field(default_factory=list)
    lender_decision: None = None
    recommendation: None = None
