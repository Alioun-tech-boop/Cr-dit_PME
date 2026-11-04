from decimal import Decimal
from typing import Protocol, Literal

from pydantic import Field, model_validator

from credit.shared.contracts import Contract


class Score(Contract):
    value: Decimal = Field(ge=0, le=100)
    scale: str
    validation_version: str
    usable: bool
    orientation: Literal["higher_is_more_solvent"] = "higher_is_more_solvent"


class CriteriaEngine(Protocol):
    def evaluate(self, indicators: dict) -> Score | None: ...


class PredictiveModel(Protocol):
    def predict(self, inputs: dict) -> Score | None: ...


class CombinationPolicy(Contract):
    version: str = "70-30-v1"
    criteria_weight: Decimal = Decimal("0.70")
    model_weight: Decimal = Decimal("0.30")

    @model_validator(mode="after")
    def fixed_weights(self):
        if self.criteria_weight != Decimal("0.70") or self.model_weight != Decimal("0.30"):
            raise ValueError("Politique duale fixée à 70/30")
        return self

    def combine(self, criteria: Score | None, model: Score | None):
        """Opération arithmétique héritée ; les moteurs détaillés valident aussi profil/produit/modèle."""
        if not criteria or not model or not criteria.usable or not model.usable:
            return None
        if (
            criteria.scale != model.scale
            or criteria.orientation != "higher_is_more_solvent"
            or model.orientation != criteria.orientation
        ):
            return None
        return self.criteria_weight * criteria.value + self.model_weight * model.value


class ScoringResult(Contract):
    criteria_score: Score | None = None
    criteria_status: str = "validated_grid_not_available"
    model_score: Score | None = None
    model_status: str = "not_available"
    combined_score: Decimal | None = None
    policy: CombinationPolicy = Field(default_factory=CombinationPolicy)
