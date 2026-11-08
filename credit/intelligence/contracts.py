"""Contrats d'entrée des niveaux décisionnel et institutionnel.

Les montants sont des Decimal exacts (chaîne décimale ou entier). Les flottants
sont refusés pour éviter toute dérive binaire sur des montants monétaires.
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator, model_validator

from credit.shared.contracts import Contract


def _exact(value):
    if isinstance(value, (float, bool)):
        raise ValueError("Montant : chaîne décimale ou entier exact requis, pas de flottant")
    return value


RiskLevel = Literal["low", "moderate", "high", "critical"]
Recommendation = Literal[
    "favorable", "favorable_sous_conditions", "analyse_complementaire_necessaire", "defavorable"
]


class DecisionRequest(Contract):
    assessment_id: str = Field(min_length=1, max_length=36)
    guarantee_amount: Decimal | None = Field(default=None, ge=0, max_digits=24, decimal_places=2)
    requested_duration_months: int | None = Field(default=None, ge=1, le=600)
    run_standard_scenarios: bool = True
    human_notes: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("guarantee_amount", mode="before")
    @classmethod
    def exact_guarantee(cls, value):
        return _exact(value)


class PublishRequest(Contract):
    note: str | None = Field(default=None, max_length=2000)


class GuaranteeCreate(Contract):
    decision_analysis_id: str = Field(min_length=1, max_length=36)
    partner_id: str | None = Field(default=None, max_length=36)
    approved_amount: Decimal | None = Field(default=None, ge=0, max_digits=24, decimal_places=2)
    sector: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    risk_level: RiskLevel | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    conditions: list[str] = Field(default_factory=list, max_length=100)
    reference: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("approved_amount", mode="before")
    @classmethod
    def exact_amount(cls, value):
        return _exact(value)

    @model_validator(mode="after")
    def dates(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("Période de garantie inversée")
        return self


class GuaranteeAction(Contract):
    action: Literal[
        "submit",
        "approve",
        "reject",
        "transmit",
        "activate",
        "expire",
        "mobilize",
        "close",
    ]
    reason: str = Field(min_length=3, max_length=1000)
    approved_amount: Decimal | None = Field(default=None, ge=0, max_digits=24, decimal_places=2)
    effective_from: date | None = None
    effective_to: date | None = None

    @field_validator("approved_amount", mode="before")
    @classmethod
    def exact_amount(cls, value):
        return _exact(value)

    @model_validator(mode="after")
    def dates(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("Période de garantie inversée")
        return self


class ClaimCreate(Contract):
    guarantee_id: str = Field(min_length=1, max_length=36)
    reference: str = Field(min_length=1, max_length=100)
    declared_amount: Decimal = Field(ge=0, max_digits=24, decimal_places=2)
    reason: str = Field(min_length=3, max_length=2000)
    documents_received: bool = False

    @field_validator("declared_amount", mode="before")
    @classmethod
    def exact_amount(cls, value):
        return _exact(value)


class ClaimAction(Contract):
    action: Literal[
        "receive_documents",
        "verify_conditions",
        "assess_amount",
        "approve",
        "pay",
        "record_recovery",
        "close",
        "reject",
    ]
    amount: Decimal | None = Field(default=None, ge=0, max_digits=24, decimal_places=2)
    reason: str = Field(min_length=3, max_length=2000)

    @field_validator("amount", mode="before")
    @classmethod
    def exact_amount(cls, value):
        return _exact(value)


class CapacityUpsert(Contract):
    as_of: date
    own_funds: Decimal | None = Field(default=None, ge=0, max_digits=24, decimal_places=2)
    mobilizable_resources: Decimal | None = Field(default=None, ge=0, max_digits=24, decimal_places=2)
    liquidities: Decimal | None = Field(default=None, ge=0, max_digits=24, decimal_places=2)
    provisions: Decimal | None = Field(default=None, ge=0, max_digits=24, decimal_places=2)
    safety_reserve: Decimal | None = Field(default=None, ge=0, max_digits=24, decimal_places=2)
    max_global_exposure: Decimal | None = Field(default=None, ge=0, max_digits=24, decimal_places=2)
    coverage_limit: Decimal | None = Field(default=None, ge=0, le=10, max_digits=12, decimal_places=6)
    max_sector_share: Decimal | None = Field(default=None, ge=0, le=1, max_digits=12, decimal_places=6)
    max_bank_share: Decimal | None = Field(default=None, ge=0, le=1, max_digits=12, decimal_places=6)
    max_borrower_share: Decimal | None = Field(default=None, ge=0, le=1, max_digits=12, decimal_places=6)
    source_reference: str | None = Field(default=None, max_length=300)

    @field_validator(
        "own_funds",
        "mobilizable_resources",
        "liquidities",
        "provisions",
        "safety_reserve",
        "max_global_exposure",
        "coverage_limit",
        "max_sector_share",
        "max_bank_share",
        "max_borrower_share",
        mode="before",
    )
    @classmethod
    def exact_amounts(cls, value):
        return _exact(value)


class LimitUpsert(Contract):
    scope: Literal["global", "sector", "bank", "borrower", "region"]
    key: str = Field(min_length=1, max_length=120)
    max_amount: Decimal | None = Field(default=None, ge=0, max_digits=24, decimal_places=2)
    max_share: Decimal | None = Field(default=None, ge=0, le=1, max_digits=12, decimal_places=6)
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("max_amount", "max_share", mode="before")
    @classmethod
    def exact_amounts(cls, value):
        return _exact(value)


class StressScenario(Contract):
    id: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=200)
    kind: Literal[
        "default_rate_increase",
        "simultaneous_default",
        "sector_degradation",
        "concentration",
        "mobilization",
        "resource_degradation",
    ]
    default_rate: Decimal | None = Field(default=None, ge=0, le=1, max_digits=12, decimal_places=6)
    guarantee_ids: list[str] = Field(default_factory=list, max_length=200)
    count: int | None = Field(default=None, ge=0, le=10000)
    sector: str | None = Field(default=None, max_length=120)
    share: Decimal | None = Field(default=None, ge=0, le=1, max_digits=12, decimal_places=6)
    amount: Decimal | None = Field(default=None, ge=0, max_digits=24, decimal_places=2)
    resource_reduction: Decimal | None = Field(
        default=None, ge=0, le=1, max_digits=12, decimal_places=6
    )
    rationale: str = Field(min_length=3, max_length=2000)

    @field_validator("default_rate", "share", "amount", "resource_reduction", mode="before")
    @classmethod
    def exact_amounts(cls, value):
        return _exact(value)


class StressRequest(Contract):
    scenarios: list[StressScenario] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique(self):
        if len({s.id for s in self.scenarios}) != len(self.scenarios):
            raise ValueError("Identifiants de scénario dupliqués")
        return self
