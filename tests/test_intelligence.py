"""Niveaux 1 à 3 : formules déterministes, transitions et confidentialité.

Les tests ne supposent aucune donnée institutionnelle réelle : la capacité est
configurée explicitement dans le test, sinon l'état `not_configured` est attendu.
"""

import hashlib
import json
from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from credit.api import create_app
from credit.application import CONTRACTS
from credit.financial_v2.engines import IndividualAnalysisEngine
from credit.intelligence import DECISION_RULES_VERSION, FINANCIAL_RULES_VERSION
from credit.intelligence import decision as decision_rules
from credit.intelligence import financial as financial_rules
from credit.intelligence import institutional as institutional_rules
from credit.intelligence.contracts import DecisionRequest

ROOT = Path("examples/assessments")


def synthetic_report():
    case = CONTRACTS["individuals"].model_validate_json(
        (ROOT / "individual_control.json").read_text()
    )
    report = IndividualAnalysisEngine().analyze(case).model_dump(mode="json")
    return report, case.model_dump(mode="json")


def auth(user):
    return {"Authorization": "Bearer intel-" + user}


@pytest.fixture
def intel(url, local_identities, monkeypatch):
    users = [
        {
            "id": "manager",
            "role": "institution_manager",
            "institution_id": "issuer",
            "token_sha256": hashlib.sha256(b"intel-manager").hexdigest(),
            "case_ids": [],
        },
        {
            "id": "analyst",
            "role": "analyst",
            "institution_id": "issuer",
            "token_sha256": hashlib.sha256(b"intel-analyst").hexdigest(),
            "case_ids": [],
        },
        {
            "id": "applicant",
            "role": "applicant",
            "institution_id": "issuer",
            "token_sha256": hashlib.sha256(b"intel-applicant").hexdigest(),
            "case_ids": [],
        },
    ]
    local_identities.write_text(json.dumps({"users": users}))
    monkeypatch.setenv("CREDIT_ENV", "local")
    monkeypatch.setenv("CREDIT_RATE_REQUESTS", "10000")
    monkeypatch.setenv("CREDIT_RATE_ACTOR", "10000")
    monkeypatch.setenv("CREDIT_RATE_JOBS", "10000")
    with TestClient(create_app(url)) as client:
        client.identities = local_identities
        yield client


def grant_case(client, case_id, user="applicant"):
    data = json.loads(client.identities.read_text())
    for item in data["users"]:
        if item["id"] == user:
            item["case_ids"] = [case_id]
    client.identities.write_text(json.dumps(data))


def prepared_case():
    payload = json.loads((ROOT / "individual_control.json").read_text())
    # La fraîcheur est une règle explicite : le test fixe la date de référence
    # au jour d'exécution pour ne pas dépendre de l'horloge du serveur.
    payload["analysis_details"]["as_of"] = date.today().isoformat()
    return payload


# ---------------------------------------------------------------------------
# Niveau 1 — intelligence financière
# ---------------------------------------------------------------------------


def test_financial_score_is_explainable_reproducible_and_not_a_probability():
    report, case = synthetic_report()
    first = financial_rules.build_financial_intelligence(report, case)
    second = financial_rules.build_financial_intelligence(deepcopy(report), deepcopy(case))

    assert first == second
    assert first["rules_version"] == FINANCIAL_RULES_VERSION
    assert first["score"]["status"] == "available"
    assert Decimal(0) <= Decimal(first["score"]["value"]) <= Decimal(100)
    assert first["score"]["formula"]
    assert all(criterion["formula"] for criterion in first["criteria"])
    assert first["trends"]["notice"]
    assert first["default_risk"]["probability_of_default"] is None
    assert first["default_risk"]["calibrated"] is False
    assert "probabilité" in first["default_risk"]["statement"].lower()
    assert all(criterion["available"] for criterion in first["criteria"] if criterion["critical"])


def test_missing_critical_data_blocks_score_and_is_reported():
    report, case = synthetic_report()
    mutated = deepcopy(report)
    for row in mutated["financial_calculations"]["periods"]:
        row["margin_after_credit"] = None
        row["available_before_debt"] = None
        row["existing_debt_service"] = None
        row["new_debt_service"] = None

    result = financial_rules.build_financial_intelligence(mutated, case)
    assert result["score"]["status"] == "incomplet"
    assert result["score"]["value"] is None
    assert result["missing_criteria"]
    assert any(risk["id"] == "incomplete_data" for risk in result["risks"])
    assert result["default_risk"]["probability_of_default"] is None


# ---------------------------------------------------------------------------
# Niveau 2 — recommandation de garantie
# ---------------------------------------------------------------------------


def decision_inputs():
    intelligence = {
        "score": {
            "value": "78.00",
            "label": "Satisfaisant",
            "risk_level": "low",
            "coverage": "1.00000000",
            "status": "available",
        },
        "risks": [],
        "capacity": {"minimum_margin_after_debt": "50000.00"},
        "groups": [
            {"items": [{"label": "Réserve minimale projetée", "value": "100000.00"}]}
        ],
        "criteria": [
            {"id": "debt_service_ratio", "value": "0.25"},
            {"id": "dscr", "value": "1.60"},
        ],
        "core": "individuals",
    }
    reliability = {
        "level": "adequate",
        "suspended": False,
        "human_verifications": [],
    }
    scenarios = {
        "adverse": {"status": "available", "min_margin": "20000.00"},
        "severe": {"status": "available", "min_margin": "5000.00"},
    }
    affordability = {
        "requested": {"principal": "100000.00"},
        "amounts": {
            "recommended_max_amount": "120000.00",
            "amount_above_recommended": None,
        },
    }
    request = DecisionRequest(assessment_id="a", guarantee_amount="50000")
    return intelligence, reliability, scenarios, affordability, request


def test_recommendation_outcomes_are_deterministic():
    intelligence, reliability, scenarios, affordability, request = decision_inputs()
    favorable = decision_rules.build_decision(
        None, None, intelligence, reliability, scenarios, affordability, request, None
    )
    assert favorable["outcome"] == "favorable"
    assert favorable["rules_version"] == DECISION_RULES_VERSION
    assert favorable["guarantee"]["human_approval_required"] is True
    assert favorable["guarantee"]["human_approval_status"] == "pending"

    blocked = deepcopy(intelligence)
    blocked["capacity"]["minimum_margin_after_debt"] = "-1.00"
    refused = decision_rules.build_decision(
        None, None, blocked, reliability, scenarios, affordability, request, None
    )
    assert refused["outcome"] == "defavorable"
    assert refused["guarantee"]["recommended_amount"] == "0.00"

    suspended = deepcopy(reliability)
    suspended["suspended"] = True
    pending = decision_rules.build_decision(
        None, None, intelligence, suspended, scenarios, affordability, request, None
    )
    assert pending["outcome"] == "analyse_complementaire_necessaire"
    assert pending["guarantee"]["recommended_amount"] is None

    conditioned = deepcopy(affordability)
    conditioned["amounts"]["recommended_max_amount"] = "80000.00"
    conditioned["amounts"]["amount_above_recommended"] = "20000.00"
    conditional = decision_rules.build_decision(
        None, None, intelligence, reliability, scenarios, conditioned, request, None
    )
    assert conditional["outcome"] == "favorable_sous_conditions"
    assert conditional["conditions"]


def test_scenario_missing_blocks_a_plain_favorable_outcome():
    intelligence, reliability, scenarios, affordability, request = decision_inputs()
    scenarios["severe"] = {"status": "not_available", "min_margin": None}
    result = decision_rules.build_decision(
        None, None, intelligence, reliability, scenarios, affordability, request, None
    )
    assert result["outcome"] == "analyse_complementaire_necessaire"


# ---------------------------------------------------------------------------
# Niveau 3 — capacité, portefeuille, stress et sinistres
# ---------------------------------------------------------------------------


def portfolio_fixture():
    config = {
        "as_of": "2026-01-31",
        "own_funds": "1000000",
        "mobilizable_resources": "200000",
        "liquidities": "0",
        "provisions": "100000",
        "safety_reserve": "50000",
        "coverage_limit": "2",
    }
    guarantees = [
        {
            "id": "g1",
            "status": "active",
            "approved_amount": "100000",
            "partner_id": "bank-one",
            "sector": "commerce",
            "region": "centre",
            "borrower_type": "businesses",
            "risk_level": "high",
            "case_id": "case-1",
        },
        {
            "id": "g2",
            "status": "proposed",
            "requested_amount": "50000",
            "partner_id": "bank-two",
            "sector": "services",
            "region": "centre",
            "borrower_type": "individuals",
            "risk_level": "low",
            "case_id": "case-2",
        },
    ]
    return config, guarantees


def test_capacity_is_not_invented_and_uses_explicit_parameters():
    config, guarantees = portfolio_fixture()
    summary = institutional_rules.capacity_summary(config, guarantees)
    assert summary["status"] == "configured"
    assert Decimal(summary["eligible_resources"]) == Decimal("1050000")
    assert Decimal(summary["configured_cap"]) == Decimal("2100000")
    assert Decimal(summary["active_commitments"]) == Decimal("100000")
    assert Decimal(summary["remaining_capacity"]) == Decimal("2000000")

    missing = institutional_rules.capacity_summary(None, guarantees)
    assert missing["status"] == "not_configured"
    assert missing["remaining_capacity"] is None
    assert missing["alerts"]


def test_portfolio_concentration_stress_and_claims_are_distinct():
    config, guarantees = portfolio_fixture()
    portfolio = institutional_rules.portfolio_metrics(guarantees)
    assert Decimal(portfolio["totals"]["granted"]) == Decimal("150000")
    assert Decimal(portfolio["totals"]["active"]) == Decimal("100000")
    assert Decimal(portfolio["totals"]["high_risk"]) == Decimal("100000")
    assert any("risque élevé" in alert for alert in portfolio["alerts"])

    stress = institutional_rules.stress_test(
        config,
        guarantees,
        [
            {
                "id": "s1",
                "name": "Défaut conventionnel",
                "kind": "default_rate_increase",
                "default_rate": "0.10",
                "rationale": "Hypothèse explicite de test, sans probabilité calibrée.",
            }
        ],
    )
    scenario = stress["scenarios"][0]
    assert scenario["status"] == "computed"
    assert Decimal(scenario["impact_amount"]) == Decimal("20000")
    assert scenario["breach"] is False

    claims = [
        {
            "status": "closed",
            "declared_amount": "100000",
            "received_amount": "100000",
            "approved_amount": "80000",
            "paid_amount": "50000",
            "recovered_amount": "10000",
        }
    ]
    summary = institutional_rules.claim_summary(claims)
    assert Decimal(summary["totals"]["declared"]) == Decimal("100000")
    assert Decimal(summary["totals"]["approved"]) == Decimal("80000")
    assert Decimal(summary["totals"]["paid"]) == Decimal("50000")
    assert Decimal(summary["totals"]["recovered"]) == Decimal("10000")
    assert Decimal(summary["outstanding"]) == Decimal("20000")


# ---------------------------------------------------------------------------
# Intégration HTTP : décision, publication, garantie, sinistre, confidentialité
# ---------------------------------------------------------------------------


def test_decision_publication_guarantee_claim_and_client_sanitization(intel):
    payload = prepared_case()
    created = intel.post("/individuals", json=payload, headers=auth("manager"))
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]

    analysis = intel.post(
        f"/individuals/{case_id}/financial-analyses", json={}, headers=auth("manager")
    )
    assert analysis.status_code == 201, analysis.text
    assessment_id = analysis.json()["id"]

    decision = intel.post(
        f"/individuals/{case_id}/decision-analyses",
        json={"assessment_id": assessment_id, "guarantee_amount": "50000"},
        headers=auth("manager"),
    )
    assert decision.status_code == 201, decision.text
    decision_data = decision.json()
    decision_id = decision_data["id"]
    assert decision_data["data"]["decision"]["outcome"] in {
        "favorable",
        "favorable_sous_conditions",
        "analyse_complementaire_necessaire",
        "defavorable",
    }
    assert decision_data["data"]["decision"]["guarantee"]["human_approval_required"] is True

    # Un demandeur ne peut ni créer ni lire une analyse décisionnelle interne.
    assert (
        intel.post(
            f"/individuals/{case_id}/decision-analyses",
            json={"assessment_id": assessment_id},
            headers=auth("applicant"),
        ).status_code
        in {403, 404}
    )

    published = intel.post(
        f"/individuals/{case_id}/decision-analyses/{decision_id}/publish",
        json={"note": "Communication synthétique de test."},
        headers=auth("manager"),
    )
    assert published.status_code == 200, published.text
    assert published.json()["client_visible"] is True

    grant_case(intel, case_id)
    client_view = intel.get(
        f"/individuals/{case_id}/client-analysis", headers=auth("applicant")
    )
    assert client_view.status_code == 200, client_view.text
    body = client_view.json()
    serialized = json.dumps(body)
    assert body["confidentiality"]["institutional_capacity_exposed"] is False
    assert body["confidentiality"]["portfolio_exposed"] is False
    for forbidden in (
        "own_funds",
        "eligible_resources",
        "remaining_capacity",
        "configured_cap",
        "active_commitments",
        "mobilizable_resources",
    ):
        assert forbidden not in serialized
    assert body["traceability"]["input_sha256"]
    assert body["score"]["value"] is not None
    assert body["default_risk"]["probability_of_default"] is None

    # Cycle de vie d'une garantie, avec validation humaine explicite.
    guarantee = intel.post(
        "/risk/guarantees",
        json={
            "decision_analysis_id": decision_id,
            "approved_amount": "50000",
            "sector": "commerce",
            "region": "centre",
            "reference": "GAR-TEST-1",
        },
        headers=auth("manager"),
    )
    assert guarantee.status_code == 201, guarantee.text
    guarantee_id = guarantee.json()["id"]
    assert guarantee.json()["status"] == "proposed"

    for action, body, expected in [
        ("submit", {"reason": "Soumission synthétique."}, "pending_validation"),
        (
            "approve",
            {"reason": "Validation humaine synthétique.", "approved_amount": "40000"},
            "approved",
        ),
        ("transmit", {"reason": "Transmission synthétique."}, "transmitted"),
        ("activate", {"reason": "Activation synthétique."}, "active"),
    ]:
        response = intel.post(
            f"/risk/guarantees/{guarantee_id}/action",
            json={"action": action, **body},
            headers=auth("manager"),
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == expected

    claim = intel.post(
        "/risk/claims",
        json={
            "guarantee_id": guarantee_id,
            "reference": "CLAIM-TEST-1",
            "declared_amount": "30000",
            "reason": "Sinistre synthétique de test.",
        },
        headers=auth("manager"),
    )
    assert claim.status_code == 201, claim.text
    claim_id = claim.json()["id"]
    assert claim.json()["status"] == "declared"

    invalid = intel.post(
        f"/risk/claims/{claim_id}/action",
        json={"action": "pay", "amount": "1000", "reason": "Paiement prématuré."},
        headers=auth("manager"),
    )
    assert invalid.status_code == 422

    for action, body, expected in [
        ("receive_documents", {"reason": "Justificatifs reçus."}, "documents_received"),
        ("verify_conditions", {"reason": "Conditions vérifiées."}, "conditions_verified"),
        (
            "assess_amount",
            {"reason": "Montant évalué.", "amount": "25000"},
            "amount_assessed",
        ),
        ("approve", {"reason": "Montant approuvé.", "amount": "20000"}, "approved"),
        ("pay", {"reason": "Paiement partiel.", "amount": "15000"}, "paid"),
        ("record_recovery", {"reason": "Recouvrement.", "amount": "5000"}, "recovery"),
        ("close", {"reason": "Dossier clos."}, "closed"),
    ]:
        response = intel.post(
            f"/risk/claims/{claim_id}/action",
            json={"action": action, **body},
            headers=auth("manager"),
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == expected

    portfolio = intel.get("/risk/portfolio", headers=auth("manager"))
    assert portfolio.status_code == 200, portfolio.text
    portfolio_body = portfolio.json()
    assert Decimal(portfolio_body["claims"]["totals"]["declared"]) == Decimal("30000")
    assert Decimal(portfolio_body["claims"]["totals"]["paid"]) == Decimal("15000")
    assert Decimal(portfolio_body["claims"]["totals"]["recovered"]) == Decimal("5000")

    assert intel.get("/risk/portfolio", headers=auth("applicant")).status_code == 403


def test_capacity_configuration_and_caps(intel):
    body = {
        "as_of": "2026-01-31",
        "own_funds": "1000000",
        "mobilizable_resources": "500000",
        "liquidities": "0",
        "provisions": "100000",
        "safety_reserve": "50000",
        "coverage_limit": "2",
    }
    saved = intel.put("/risk/capacity", json=body, headers=auth("manager"))
    assert saved.status_code == 200, saved.text

    read = intel.get("/risk/capacity", headers=auth("manager"))
    assert read.status_code == 200, read.text
    data = read.json()
    assert data["status"] == "configured"
    assert Decimal(data["eligible_resources"]) == Decimal("1350000")
    assert Decimal(data["configured_cap"]) == Decimal("2700000")

    assert intel.put("/risk/capacity", json=body, headers=auth("analyst")).status_code == 403
