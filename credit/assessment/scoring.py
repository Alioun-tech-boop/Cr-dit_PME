"""Scoring explicable distinct des constats financiers et de toute décision de prêt."""

from datetime import date
from decimal import Decimal
from typing import Literal, Protocol
from pydantic import Field

from credit.shared.contracts import Contract
from credit.assessment.contracts import RuleResult
from credit.shared.schedule import rounded
from credit.shared.arithmetic import deterministic


class ValidatedScore(Contract):
    value: Decimal = Field(ge=0, le=100)
    scale: str = "solvency_0_100"
    orientation: str = "higher_is_more_solvent"
    validated: bool
    validation_reference: str
    validation_date: date
    model_version: str
    profile: str
    product_id: str
    population: str
    required_data_complete: bool


class CalibratedPD(Contract):
    value: Decimal = Field(ge=0, le=1)
    calibrated: bool
    required_data_complete: bool = False
    validated: bool
    default_definition: str = Field(min_length=1)
    horizon_months: int = Field(gt=0)
    population: str = Field(min_length=1)
    profile: str
    product_id: str
    model_version: str
    validation_date: date
    validation_reference: str = Field(min_length=1)


class LossParameter(Contract):
    value: Decimal = Field(ge=0)
    kind: Literal["LGD", "EAD"]
    justified: bool
    reference: str = Field(min_length=1)
    horizon_months: int = Field(gt=0)
    population: str
    profile: str
    product_id: str
    currency: Literal["XOF"] = "XOF"
    unit: Literal["fraction", "XOF"]


class Prediction(Contract):
    score: ValidatedScore | None = None
    pd: CalibratedPD | None = None
    lgd: LossParameter | None = None
    ead: LossParameter | None = None


class PredictiveAdapter(Protocol):
    def predict(self, features: dict) -> Prediction: ...


@deterministic
def expected_loss(pd, lgd, ead):
    unavailable = {
        "status": "not_available",
        "value": None,
        "currency": "XOF",
        "explanation": "PD calibrée, LGD et EAD justifiées, de même horizon et périmètre, nécessaires.",
    }
    if (
        not pd
        or not lgd
        or not ead
        or not pd.validated
        or not pd.calibrated
        or not pd.required_data_complete
        or not lgd.justified
        or not ead.justified
    ):
        return unavailable
    attrs = ["horizon_months", "population", "profile", "product_id"]
    if any(getattr(pd, k) != getattr(lgd, k) or getattr(pd, k) != getattr(ead, k) for k in attrs):
        return unavailable
    if (
        lgd.kind != "LGD"
        or ead.kind != "EAD"
        or lgd.unit != "fraction"
        or ead.unit != "XOF"
        or lgd.value > 1
        or lgd.currency != ead.currency
    ):
        return unavailable
    return {
        "status": "available",
        "value": rounded(pd.value * lgd.value * ead.value),
        "currency": ead.currency,
        "formula": "PD × LGD × EAD",
        "horizon_months": pd.horizon_months,
        "references": [pd.validation_reference, lgd.reference, ead.reference],
    }


def compatible(score, policy, profile, product, as_of):
    return bool(
        score
        and score.validated
        and score.required_data_complete
        and score.validation_reference.strip()
        and score.population.strip()
        and score.scale == policy.scale
        and score.orientation == policy.orientation
        and score.profile == profile
        and score.product_id == product
        and product == policy.product.id
        and score.population in policy.model_populations
        and score.validation_date <= as_of
    )


def known_path(ctx, path):
    from pydantic import BaseModel
    from credit.shared.contracts import Amount, SignedAmount

    def visit(node, parts):
        if not parts:
            if isinstance(node, (Amount, SignedAmount)):
                return ctx.reader.amount(node, path) is not None
            if isinstance(node, list):
                return bool(node)
            return node is not None and node != ""
        if node is None:
            return False
        part, *tail = parts
        if part == "*":
            return isinstance(node, list) and all(visit(v, tail) for v in node)
        if isinstance(node, BaseModel):
            return part in type(node).model_fields and visit(getattr(node, part), tail)
        if isinstance(node, list) and part.isdigit() and int(part) < len(node):
            return visit(node[int(part)], tail)
        return False

    return visit(ctx.case, path.split("."))


def score_report(ctx, sections, policy, mode, model=None):
    result = {
        "criteria_score": None,
        "criteria_status": "approved_policy_not_available",
        "criteria_validation_status": None,
        "combined_score": None,
        "solvency_score": None,
        "risk_index": None,
        "risk_index_basis": None,
        "orientation": "higher_is_more_solvent",
        "scale": "solvency_0_100",
        "is_default_probability": False,
        "model_status": "not_available",
        "model_result": None,
        "probability_of_default": None,
        "mode": "indicators_only",
        "policy_id": None,
        "policy_version": None,
        "criteria_trace": [],
        "combination_policy": "dual-70-30-v1",
        "expected_loss": expected_loss(None, None, None),
    }
    if policy is None:
        return result
    result.update(
        policy_id=policy.id,
        policy_version=policy.version,
        criteria_validation_status=policy.validation_status,
    )
    missing = []
    scores = []
    section_values = {}
    for criterion in policy.criteria:
        section = next((s for s in sections if s.id == criterion.section_id), None)
        metric = (
            next((m for m in section.indicators if m.id == criterion.metric_id), None)
            if section
            else None
        )
        missing_fields = [
            field for field in criterion.critical_fields if not known_path(ctx, field)
        ]
        if (
            section is None
            or section.status in {"incomplet", "non_applicable"}
            or metric is None
            or metric.value is None
            or metric.unit != criterion.unit
            or missing_fields
        ):
            missing.append(criterion.id)
            result["criteria_trace"].append(
                {
                    "id": criterion.id,
                    "status": "not_evaluable",
                    "weight": criterion.weight,
                    "missing_critical_fields": missing_fields,
                    "score": None,
                    "reason": "Section, unité ou donnée critique indisponible ; poids non redistribué.",
                }
            )
            if section:
                section.rules.append(
                    RuleResult(
                        id="criterion:" + criterion.id,
                        version=policy.version,
                        indicator_id=criterion.metric_id,
                        operator="not_evaluable",
                        threshold=None,
                        observed=metric.value if metric else None,
                        passed=None,
                        explanation="Critère indisponible, aucun score imputé ou poids renormalisé.",
                        validation_status=policy.validation_status,
                    )
                )
            continue
        value = metric.value
        band = next(
            b
            for b in criterion.bands
            if (b.lower is None or value >= b.lower) and (b.upper is None or value < b.upper)
        )
        section.rules.append(
            RuleResult(
                id="criterion:" + criterion.id,
                version=policy.version,
                indicator_id=criterion.metric_id,
                operator="lower_inclusive_upper_exclusive",
                threshold=band.lower,
                observed=value,
                passed=band.status == "favorable",
                explanation=f"Politique {policy.id}, {policy.validation_status} : [{band.lower}, {band.upper}[ ; score {band.score}, poids fixe {criterion.weight}.",
                validation_status=policy.validation_status,
            )
        )
        scores.append(criterion.weight * band.score)
        section_values.setdefault(section.id, []).append((criterion.weight, band.score))
        result["criteria_trace"].append(
            {
                "id": criterion.id,
                "status": "evaluated",
                "metric": criterion.metric_id,
                "value": value,
                "weight": criterion.weight,
                "score": band.score,
                "band": band.model_dump(mode="json"),
                "phenomenon": criterion.phenomenon,
                "formula": "poids fixe × score de la bande",
            }
        )
    if ctx.financial.status == "incomplete":
        missing += ctx.financial.information_requested
    missing.extend(
        s.id
        for s in sections
        if s.id in policy.required_sections and s.status in {"incomplet", "non_applicable"}
    )
    for section in sections:
        expected = sum(c.section_id == section.id for c in policy.criteria)
        values = section_values.get(section.id, [])
        if expected and len(values) == expected:
            section.score = sum(w * v for w, v in values) / sum(w for w, _ in values)
            section.score_validation_status = policy.validation_status
    if missing:
        result.update(
            criteria_status="missing_data_or_non_applicable", missing_criteria=sorted(set(missing))
        )
    else:
        criteria = sum(scores)
        result.update(
            criteria_score=criteria,
            criteria_status="available",
            solvency_score=criteria,
            risk_index=100 - criteria,
            risk_index_basis="criteria",
            mode="criteria_only",
        )
    profile = getattr(ctx.case, "profile", getattr(ctx.case, "mode", None))
    product = ctx.details.funding.product_id
    as_of = ctx.details.as_of
    if model is None:
        return result
    if not (
        policy.allow_model
        and policy.validation_status == "approved"
        and as_of
        and product == policy.product.id
        and ctx.financial.status == "complete"
        and all(known_path(ctx, p) for p in policy.model_required_fields)
    ):
        result["model_status"] = "policy_or_data_does_not_allow_model"
        return result
    try:
        prediction = Prediction.model_validate(
            model.predict(
                {
                    "case": ctx.case.model_dump(mode="json"),
                    "financial": ctx.financial.model_dump(mode="json"),
                }
            )
        )
    except Exception:
        result["model_status"] = "not_available"
        result["model_unavailable_reason"] = (
            "Le fournisseur de modèle n’a pas retourné un contrat utilisable."
        )
        return result
    result["model_result"] = prediction.model_dump(mode="json")
    score = prediction.score
    if compatible(score, policy, profile, product, as_of):
        result["model_status"] = "validated_compatible"
        if result["criteria_score"] is not None:
            combined = Decimal("0.70") * result["criteria_score"] + Decimal("0.30") * score.value
            result.update(
                combined_score=combined,
                solvency_score=combined,
                risk_index=100 - combined,
                risk_index_basis="combined",
                mode="dual_70_30",
            )
    else:
        result["model_status"] = "incompatible_or_not_validated"
    pd = prediction.pd
    if (
        pd
        and pd.validated
        and pd.calibrated
        and pd.required_data_complete
        and pd.profile == profile
        and pd.product_id == product
        and pd.population in policy.model_populations
        and pd.validation_date <= as_of
    ):
        if prediction.score is None:
            result["model_status"] = "validated_pd_only"
        result["probability_of_default"] = pd.model_dump(mode="json")
        result["expected_loss"] = expected_loss(pd, prediction.lgd, prediction.ead)
    return result
