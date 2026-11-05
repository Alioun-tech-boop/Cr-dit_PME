from __future__ import annotations
from datetime import date as Date
from decimal import Decimal
from typing import Literal
from pydantic import Field, model_validator
from credit.shared.contracts import Contract, Amount, SignedAmount, Payment
from credit.assessment.api_contracts import ReviewedValueBinding
from credit.assessment.contracts import AssessmentReport


class Source(Contract):
    kind: Literal["calculation", "internal_policy", "verified_reference"] = "internal_policy"
    reference: str = Field(min_length=1)
    url: str | None = None
    date: Date | None = None
    scope: str = Field(min_length=1)
    verification_status: Literal["not_verified", "human_verified"] = "not_verified"
    verified_by: str | None = None
    regulatory: bool = False

    @model_validator(mode="after")
    def regulatory_verified(self):
        if self.regulatory and (
            self.kind != "verified_reference"
            or not self.url
            or not self.date
            or self.verification_status != "human_verified"
            or not self.verified_by
        ):
            raise ValueError(
                "Référence réglementaire : source, date, périmètre et revue humaine requis"
            )
        return self


class Rule(Contract):
    id: str
    version: str
    metric: str
    operator: Literal["ge", "gt", "le", "lt", "eq"]
    threshold: Decimal
    required_fields: list[str] = Field(default_factory=list)
    justification: str = Field(min_length=1)
    severity: Literal["information", "vigilance", "mandatory_review"]
    effect: Literal["favorable", "vigilance", "defavorable"] = "vigilance"
    source: Source
    phenomenon: str
    weight: Decimal | None = Field(default=None, gt=0, le=1)


class Tariff(Contract):
    min_amount: Decimal = Field(ge=0)
    max_amount: Decimal = Field(gt=0)
    min_months: int = Field(ge=1, le=600)
    max_months: int = Field(ge=1, le=600)
    annual_rate: Decimal = Field(ge=0, le=10)
    fee_per_payment: Decimal = Field(ge=0)
    reference: str = Field(min_length=1)

    @model_validator(mode="after")
    def limits(self):
        if self.max_amount < self.min_amount or self.max_months < self.min_months:
            raise ValueError("Barème inversé")
        return self


class Product(Contract):
    id: str
    min_amount: Decimal = Field(gt=0)
    max_amount: Decimal = Field(gt=0)
    min_months: int = Field(ge=1, le=600)
    max_months: int = Field(ge=1, le=600)
    schedules: list[Literal["monthly_constant", "explicit"]]
    allowed_due_days: list[int] = Field(min_length=1)
    allowed_grace_months: list[int] = Field(default_factory=lambda: [0])
    grace_interest_treatment: Literal["not_configured", "interest_only"] = "not_configured"
    tariffs: list[Tariff] = Field(default_factory=list, max_length=100)
    minimum_contribution_share: Decimal | None = Field(default=None, ge=0, le=1)
    minimum_margin: Decimal | None = None
    minimum_reserve: Decimal | None = None
    minimum_debt_coverage: Decimal | None = Field(default=None, gt=0)
    allow_unchanged_contract_pricing: bool = False

    @model_validator(mode="after")
    def coherent(self):
        if (
            self.min_amount > self.max_amount
            or self.min_months > self.max_months
            or any(not 1 <= d <= 31 for d in self.allowed_due_days)
        ):
            raise ValueError("Limites de produit incohérentes")
        if any(g < 0 or g > self.max_months for g in self.allowed_grace_months):
            raise ValueError("Différé hors des limites du produit")
        for i, a in enumerate(self.tariffs):
            for b in self.tariffs[i + 1 :]:
                if max(a.min_amount, b.min_amount) <= min(a.max_amount, b.max_amount) and max(
                    a.min_months, b.min_months
                ) <= min(a.max_months, b.max_months):
                    raise ValueError("Barèmes ambigus ou chevauchants")
        return self


class Policy(Contract):
    id: str
    version: str
    core: Literal["individuals", "businesses"]
    profiles: list[str] = Field(min_length=1)
    institution_id: str | None = None
    validation_status: Literal["approved", "illustrative_not_validated"]
    approved_by: str | None = None
    approved_on: Date | None = None
    approval_reference: str | None = None
    product: Product
    minimum_history_periods: int = Field(default=3, ge=2, le=120)
    seasonality_minimum_months: int = Field(default=24, ge=24, le=120)
    scoring_enabled: bool = False
    missing_data: Literal["block_score"] = "block_score"
    orientation: Literal["higher_is_more_solvent"] = "higher_is_more_solvent"
    rules: list[Rule] = Field(default_factory=list, max_length=100)
    required_scenarios: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def approval_and_weights(self):
        if self.validation_status == "approved" and not all(
            [self.approved_by, self.approved_on, self.approval_reference]
        ):
            raise ValueError("Approbation métier explicite nécessaire")
        if len({r.id for r in self.rules}) != len(self.rules) or len(
            {r.phenomenon for r in self.rules}
        ) != len(self.rules):
            raise ValueError("Règle ou phénomène redondant")
        weighted = [r for r in self.rules if r.weight is not None]
        if self.scoring_enabled and (not weighted or sum(r.weight for r in weighted) != 1):
            raise ValueError("La somme des poids doit être exactement 1")
        if not self.scoring_enabled and weighted:
            raise ValueError("Poids sans scoring activé")
        return self


class AccountReconciliation(Contract):
    id: str
    start: Date
    end: Date
    currency: Literal["XOF"] = "XOF"
    unit_multiplier: Literal["1", "1000", "1000000"]
    opening: SignedAmount
    inflows: Amount
    outflows: Amount
    closing: SignedAmount
    evidence_ids: list[str] = Field(default_factory=list)
    scope: Literal["this_account_only"] = "this_account_only"

    @model_validator(mode="after")
    def ordered(self):
        if self.end < self.start:
            raise ValueError("Période de rapprochement inversée")
        return self


class CostSplit(Contract):
    period: Date
    fixed: Amount
    variable: Amount
    complete: bool


class SourceClassification(Contract):
    source: str
    frequency: Literal["recurring", "exceptional", "unknown"]
    evidence_ids: list[str] = Field(default_factory=list)


class BalanceSheet(Contract):
    as_of: Date
    currency: Literal["XOF"] = "XOF"
    unit_multiplier: Literal["1", "1000", "1000000"]
    stable_resources: SignedAmount | None = None
    fixed_assets: Amount | None = None
    current_assets: Amount | None = None
    current_liabilities: Amount | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class AgingItem(Contract):
    reference: str
    side: Literal["customer", "supplier"]
    invoice_date: Date
    due_date: Date | None = None
    as_of: Date
    outstanding: Amount
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ordered(self):
        if self.as_of < self.invoice_date or (self.due_date and self.due_date < self.invoice_date):
            raise ValueError("Dates de créance ou dette incohérentes")
        return self


class Facts(Contract):
    accounts: list[AccountReconciliation] = Field(default_factory=list, max_length=100)
    cost_splits: list[CostSplit] = Field(default_factory=list, max_length=600)
    source_classifications: list[SourceClassification] = Field(default_factory=list, max_length=100)
    balance_sheets: list[BalanceSheet] = Field(default_factory=list, max_length=100)
    aging: list[AgingItem] = Field(default_factory=list, max_length=1000)
    tax_basis: Literal["net_of_tax", "gross_of_tax", "unknown"] = "unknown"
    supplier_flows_complete: bool = False

    @model_validator(mode="after")
    def unambiguous_details(self):
        for rows, attr in [
            (self.cost_splits, "period"),
            (self.source_classifications, "source"),
            (self.balance_sheets, "as_of"),
            (self.aging, "reference"),
        ]:
            if len({getattr(row, attr) for row in rows}) != len(rows):
                raise ValueError("Ventilation ou référence complémentaire dupliquée : " + attr)
        return self


class Stress(Contract):
    id: str
    name: str
    revenue_drop: Decimal = Field(default=Decimal(0), ge=0, le=1)
    expense_increase: Decimal = Field(default=Decimal(0), ge=0, le=10)
    variable_cost_increase: Decimal = Field(default=Decimal(0), ge=0, le=10)
    loss_source: str | None = None
    delay_from: Date | None = None
    delay_to: Date | None = None
    delay_amount: Decimal = Field(default=Decimal(0), ge=0, max_digits=24, decimal_places=2)
    project_delay_periods: int = Field(default=0, ge=0, le=60)
    rate_increase: Decimal = Field(default=Decimal(0), ge=0, le=10)
    rate_contract_reference: str | None = None
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def explicit_delay(self):
        if self.delay_amount and (
            not self.delay_from or not self.delay_to or self.delay_to <= self.delay_from
        ):
            raise ValueError("Retard : périodes croissantes explicites nécessaires")
        if self.rate_increase and not self.rate_contract_reference:
            raise ValueError("Référence de clause variable nécessaire à un choc de taux")
        return self


class ReverseTest(Contract):
    parameter: Literal["revenue_drop", "expense_increase", "delay_periods", "additional_instalment"]
    lower: Decimal = Field(ge=0)
    upper: Decimal = Field(ge=0)
    steps: int = Field(default=20, ge=2, le=200)
    tolerance: Decimal = Field(default=Decimal(".000001"), gt=0)
    delay_from: Date | None = None
    delay_amount: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def interval(self):
        if self.upper <= self.lower:
            raise ValueError("Intervalle de recherche vide")
        if self.parameter == "revenue_drop" and self.upper > 1:
            raise ValueError("Baisse de revenu supérieure à 100 %")
        if self.parameter == "expense_increase" and self.upper > 10:
            raise ValueError("Hausse de coûts hors limites")
        if self.parameter == "delay_periods" and (
            self.upper > 60
            or self.lower != int(self.lower)
            or self.upper != int(self.upper)
            or not self.delay_from
            or not self.delay_amount
        ):
            raise ValueError("Retard : intervalle entier, origine et montant nécessaires")
        return self


class Candidate(Contract):
    principal: Decimal = Field(gt=0, max_digits=24, decimal_places=2)
    months: int = Field(ge=1, le=600)
    contribution: Amount | None = None
    grace_months: int = Field(default=0, ge=0, le=600)
    schedule: list[Payment] | None = None
    contribution_already_in_opening_cash: bool | None = None
    contribution_evidence_ids: list[str] = Field(default_factory=list)


class AnalysisRequest(Contract):
    mode: Literal["real", "demonstration"] = "real"
    policy_id: str | None = None
    validated_sources: list[ReviewedValueBinding] = Field(default_factory=list, max_length=100)
    facts: Facts = Field(default_factory=Facts)
    scenarios: list[Stress] = Field(default_factory=list, max_length=30)
    reverse_tests: list[ReverseTest] = Field(default_factory=list, max_length=8)
    financing_candidates: list[Candidate] = Field(default_factory=list, max_length=100)


class Report(AssessmentReport):
    schema_version: str = "credit-pme.financial-analysis.v2"
    deep_analysis: dict


class PolicyException(Contract):
    limit_ids: list[str] = Field(min_length=1, max_length=30)
    reason: str = Field(min_length=10, max_length=2000)
