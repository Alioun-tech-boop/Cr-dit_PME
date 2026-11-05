import os
from pathlib import Path
from credit.financial_v2.contracts import Policy


def load_policy(policy_id):
    if policy_id is None:
        return None
    if not policy_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("Identifiant de politique invalide")
    root = Path(
        os.getenv("CREDIT_FINANCIAL_V2_POLICIES_DIR", Path(__file__).parent / "policies")
    ).resolve()
    path = root / (policy_id + ".json")
    if not path.is_file():
        raise ValueError("Politique v2 inconnue")
    return Policy.model_validate_json(path.read_text())


def authorize(policy, case, core, mode, institution_id):
    if mode == "demonstration" and case.data_classification != "synthetic":
        raise ValueError("Démonstration réservée aux dossiers synthétiques")
    if policy is None:
        return
    if (
        policy.core != core
        or getattr(case, "profile", getattr(case, "mode", None)) not in policy.profiles
    ):
        raise ValueError("Politique incompatible avec le noyau ou profil")
    if policy.product.id != case.analysis_details.funding.product_id:
        raise ValueError("Produit non couvert par la politique")
    if policy.institution_id is not None and policy.institution_id != institution_id:
        raise ValueError("Politique d’une autre institution")
    if policy.validation_status != "approved" and (
        mode != "demonstration"
        or case.data_classification != "synthetic"
        or os.getenv("CREDIT_ENV") == "production"
    ):
        raise ValueError("Politique illustrative interdite sur dossier réel ou en production")
    if policy.validation_status == "approved" and (
        not case.analysis_details.as_of or policy.approved_on > case.analysis_details.as_of
    ):
        raise ValueError("Date de référence antérieure à l’approbation de politique")


def qualify(metrics, policy, missing, force_review):
    result = {
        "mode": "deterministic_policy",
        "criteria_score": None,
        "solvency_score": None,
        "criteria_status": "not_available",
        "criteria_validation_status": policy.validation_status if policy else "not_available",
        "risk_index": None,
        "combined_score": None,
        "model_status": "disabled_by_design",
        "probability_of_default": None,
        "expected_loss": {
            "status": "not_available",
            "value": None,
            "explanation": "Aucune PD, LGD et EAD justifiées ; aucun score converti en PD.",
        },
        "mandatory_review": force_review,
        "qualification": "not_available",
        "rules": [],
    }
    if policy is None:
        return result
    scores = []
    blocked = False
    failed = []
    ops = {
        "ge": lambda a, b: a >= b,
        "gt": lambda a, b: a > b,
        "le": lambda a, b: a <= b,
        "lt": lambda a, b: a < b,
        "eq": lambda a, b: a == b,
    }
    for rule in policy.rules:
        value = metrics.get(rule.metric)
        unavailable = [f for f in rule.required_fields if metrics.get(f) is None]
        passed = None if value is None or unavailable else ops[rule.operator](value, rule.threshold)
        result["rules"].append(
            {
                **rule.model_dump(mode="json"),
                "observed": value,
                "passed": passed,
                "missing_fields": unavailable,
            }
        )
        if passed is None:
            blocked = True
        if passed is False:
            failed.append(rule.effect)
            if rule.severity == "mandatory_review":
                result["mandatory_review"] = True
        if rule.weight is not None:
            if passed is None:
                blocked = True
            else:
                scores.append(rule.weight * (100 if passed else 0))
    result["qualification"] = (
        "incomplet"
        if blocked
        else "defavorable"
        if "defavorable" in failed
        else "vigilance"
        if failed
        else "favorable"
    )
    if policy.scoring_enabled and not blocked and not missing and scores:
        score = sum(scores)
        result.update(
            criteria_score=score,
            solvency_score=score,
            risk_index=100 - score,
            criteria_status="available",
        )
    result["notice"] = (
        "Qualification conventionnelle de politique ; aucune probabilité de défaut. Déficits toujours visibles et revus."
    )
    return result
