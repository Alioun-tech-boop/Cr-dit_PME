import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from credit.shared.contracts import Contract, Scenario


class Band(Contract):
    lower: Decimal | None
    upper: Decimal | None
    score: Decimal = Field(ge=0, le=100)
    status: Literal["favorable", "vigilance", "defavorable"]


class Criterion(Contract):
    id: str
    section_id: str
    metric_id: str
    phenomenon: str
    weight: Decimal = Field(gt=0, le=1, max_digits=12, decimal_places=10)
    unit: str
    critical_fields: list[str]
    bands: list[Band] = Field(min_length=1)

    @model_validator(mode="after")
    def complete_bands(self):
        if self.bands[0].lower is not None or self.bands[-1].upper is not None:
            raise ValueError("Les bandes doivent couvrir tout l’intervalle réel")
        for band in self.bands:
            if band.lower is not None and band.upper is not None and band.upper <= band.lower:
                raise ValueError("Bande inversée ou vide")
        for previous, current in zip(self.bands, self.bands[1:]):
            if previous.upper is None or current.lower is None or previous.upper != current.lower:
                raise ValueError("Bandes non contiguës ou chevauchantes")
        return self


class ProductPolicy(Contract):
    id: str
    min_months: int = Field(ge=1, le=600)
    max_months: int = Field(ge=1, le=600)
    schedules: list[Literal["monthly_constant", "explicit"]]
    allowed_due_days: list[int] = Field(min_length=1)
    minimum_contribution_share: Decimal = Field(ge=0, le=1)
    lower_amount_factor: Decimal = Field(gt=0, lt=1)

    @model_validator(mode="after")
    def coherent(self):
        if self.max_months < self.min_months or any(
            not 1 <= day <= 31 for day in self.allowed_due_days
        ):
            raise ValueError("Limites de produit incohérentes")
        return self


class Approval(Contract):
    authority: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    approved_on: date


class AssessmentPolicy(Contract):
    id: str
    version: str
    core: Literal["individuals", "businesses"]
    validation_status: Literal["illustrative_not_validated", "approved"]
    approval: Approval | None = None
    profiles: list[str] = Field(min_length=1)
    model_populations: list[str] = Field(default_factory=list)
    model_required_fields: list[str] = Field(default_factory=list)
    orientation: Literal["higher_is_more_solvent"] = "higher_is_more_solvent"
    scale: Literal["solvency_0_100"] = "solvency_0_100"
    scoring_formula: Literal["fixed_weighted_sum"] = "fixed_weighted_sum"
    missing_sections: Literal["block_score"] = "block_score"
    non_applicable_sections: Literal["block_score"] = "block_score"
    required_sections: list[str]
    criteria: list[Criterion] = Field(min_length=1)
    mandatory_review: list[
        Literal[
            "period_deficit",
            "negative_balance",
            "incomplete_sections",
            "documentary_alert",
            "intraperiod_deficit",
        ]
    ]
    allow_model: bool = False
    product: ProductPolicy
    demonstration_stresses: list[Scenario] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_policy(self):
        if sum(c.weight for c in self.criteria) != 1:
            raise ValueError("La somme des poids doit être exactement égale à 1")
        if len({c.id for c in self.criteria}) != len(self.criteria) or len(
            {c.phenomenon for c in self.criteria}
        ) != len(self.criteria):
            raise ValueError("Critère ou phénomène financier redondant")
        if len({(c.section_id, c.metric_id) for c in self.criteria}) != len(self.criteria):
            raise ValueError("Ratio compté plusieurs fois")
        if self.allow_model and (not self.model_populations or not self.model_required_fields):
            raise ValueError("Population(s) modèle explicitement autorisée(s) nécessaire(s)")
        if self.validation_status == "approved" and self.approval is None:
            raise ValueError("Approbation métier explicite nécessaire")
        if not {"period_deficit", "negative_balance", "intraperiod_deficit"} <= set(
            self.mandatory_review
        ):
            raise ValueError("Les déficits doivent toujours imposer une revue")
        return self


def load_policy(policy_id, core, mode, classification):
    if policy_id is None:
        return None
    root = Path(
        os.getenv("CREDIT_ANALYSIS_POLICIES_DIR", Path(__file__).parent / "policies")
    ).resolve()
    if not policy_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("Identifiant de politique invalide")
    path = root / (policy_id + ".json")
    if not path.exists():
        raise ValueError("Politique inconnue : " + policy_id)
    policy = AssessmentPolicy.model_validate_json(path.read_text())
    authorize_policy(policy, core, mode, classification)
    return policy


def authorize_policy(policy, core, mode, classification):
    if policy.core != core:
        raise ValueError("Politique du mauvais noyau")
    if policy.validation_status == "illustrative_not_validated" and (
        mode != "demonstration" or classification != "synthetic"
    ):
        raise ValueError(
            "Politique illustrative interdite sur un dossier réel ou hors démonstration"
        )
