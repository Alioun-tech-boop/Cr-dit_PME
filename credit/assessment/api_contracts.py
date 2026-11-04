from datetime import date
from typing import Literal
from pydantic import Field
from credit.shared.contracts import Contract, Scenario
from credit.assessment.simulation import SimulationSpec


class ReviewedValueBinding(Contract):
    review_id: str
    field: str
    target_path: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$")
    expected_period: date


class AssessmentRequest(Contract):
    mode: Literal["real", "demonstration"] = "real"
    policy_id: str | None = None
    stress_scenarios: list[Scenario] | None = Field(default=None, max_length=20)
    validated_sources: list[ReviewedValueBinding] = Field(default_factory=list, max_length=100)


class SimulationRequest(Contract):
    specification: SimulationSpec
