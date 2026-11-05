"""Références indépendantes et invariants du parcours sans modèle."""

import json
from copy import deepcopy
from decimal import Decimal as D
from pathlib import Path
import pytest
from pydantic import ValidationError
from credit.application import CONTRACTS
from credit.financial_v2.contracts import Facts, Stress, ReverseTest, Candidate, Policy
from credit.financial_v2.engines import IndividualAnalysisEngine, BusinessAnalysisEngine
from credit.financial_v2.policy import load_policy
from credit.financial_v2.scenarios import prepare, search
from credit.financial_v2.diagnostics import statistics, reconcile


def case(name="individual_control", core="individuals"):
    return CONTRACTS[core].model_validate_json(
        Path("examples/assessments/" + name + ".json").read_text()
    )


def stress(**kw):
    return Stress(
        id="test", name="Hypothèse synthétique", rationale="Test explicite, pas une norme", **kw
    )


def test_control_and_inverse_no_model(monkeypatch):
    import credit.assessment.scoring

    monkeypatch.setattr(
        credit.assessment.scoring, "score_report", lambda *a: pytest.fail("Ancien score appelé")
    )
    c = case()
    before = c.model_dump_json()
    r = IndividualAnalysisEngine().analyze(
        c,
        scenarios=[stress(revenue_drop=D(".2"))],
        reverse_tests=[
            ReverseTest(parameter="revenue_drop", lower=0, upper=1, tolerance=D(".00000001")),
            ReverseTest(
                parameter="additional_instalment", lower=0, upper=100000, tolerance=D(".01")
            ),
        ],
    )
    assert r.financial_calculations["periods"][0]["margin_after_credit"] == "70000.00"
    assert r.comparisons[0]["minimum_margin_after"] == -30000
    reverse = r.deep_analysis["reverse_tests"][0]
    assert abs(reverse["threshold"] - D(".14")) < D(".0000001")
    assert reverse["analytical_cross_checks"][0]["income_annulling_margin"] == 430000
    assert reverse["analytical_cross_checks"][0]["drop_annulling_margin"] == D(".14")
    assert abs(r.deep_analysis["reverse_tests"][1]["threshold"] - 70000) < D(".02")
    assert r.scoring["model_status"] == "disabled_by_design"
    assert r.scoring["combined_score"] is r.scoring["probability_of_default"] is None
    assert c.model_dump_json() == before
    assert "70-30" not in json.dumps(r.financial_calculations)
    assert (
        r.model_dump_json()
        == IndividualAnalysisEngine()
        .analyze(
            c,
            scenarios=[stress(revenue_drop=D(".2"))],
            reverse_tests=[
                ReverseTest(parameter="revenue_drop", lower=0, upper=1, tolerance=D(".00000001")),
                ReverseTest(
                    parameter="additional_instalment", lower=0, upper=100000, tolerance=D(".01")
                ),
            ],
        )
        .model_dump_json()
    )


def test_business_reference(business):
    # Les seules données du contrôle : 4m − 3m − 250k − 400k = 350k.
    for p in business["periods"]:
        p["receipts"]["value"] = "4000000"
        p["operating_expenses"]["value"] = "3000000"
        for k in ["taxes", "essential_investments", "household_withdrawals"]:
            p[k] = {"value": "0"}
    for loan, value in [
        (business["existing_loans"][0], 250000),
        (business["requested_loan"], 400000),
    ]:
        for row in loan["schedule"]:
            row["principal"] = {"value": str(value)}
            row["interest"] = {"value": "0"}
            row["fees"] = {"value": "0"}
        loan["principal"] = {"value": str(value * len(loan["schedule"]))}
    for i, p in enumerate(business["periods"]):
        p["requested_loan_disbursement"] = {
            "value": business["requested_loan"]["principal"]["value"] if i == 0 else "0"
        }
        p["financed_uses"] = deepcopy(p["requested_loan_disbursement"])
    c = CONTRACTS["businesses"].model_validate(business)
    r = BusinessAnalysisEngine().analyze(c)
    row = r.financial_calculations["periods"][0]
    assert D(row["cash_available_for_debt"]) == 1000000
    assert D(row["margin_after_debt"]) == 350000
    assert abs(D(row["debt_service_coverage"]) - D(1000000) / D(650000)) < D("1e-25")
    assert {s.id for s in r.sections} >= {
        "structure",
        "resistance",
        "treasury",
        "collateral",
        "historical_trends",
    }


@pytest.mark.parametrize("drop", ["0", ".1", ".2", ".5", "1"])
def test_monotonic_income(drop):
    c = case()
    e = IndividualAnalysisEngine()
    changed, _, _ = prepare(c, stress(revenue_drop=D(drop)), Facts())
    assert (
        e.calculate(changed).periods[0].margin_after_debt
        <= e.calculate(c).periods[0].margin_after_debt
    )


def test_missing_and_currency_and_units():
    c = case()
    c.periods[0].essential_expenses.value = None
    c.periods[0].essential_expenses.state = "unknown"
    r = IndividualAnalysisEngine().analyze(c)
    assert r.financial_calculations["periods"][0]["margin_after_credit"] is None
    assert r.financial_risk["status"] == "incomplete"
    assert r.scoring["criteria_score"] is None
    with pytest.raises(ValidationError):
        Facts.model_validate({"accounts": [{"currency": "USD"}]})
    with pytest.raises(ValidationError):
        Facts.model_validate(
            {"balance_sheets": [{"as_of": "2026-01-01", "unit_multiplier": "100"}]}
        )


def test_retard_conserves_source_and_loss_is_identified():
    c = case()
    dates = [p.period for p in c.periods]
    changed, _, _ = prepare(
        c, stress(delay_from=dates[0], delay_to=dates[1], delay_amount=100000), Facts()
    )
    assert sum(s.net.value for p in changed.periods for s in p.incomes) == sum(
        s.net.value for p in c.periods for s in p.incomes
    )
    assert IndividualAnalysisEngine().calculate(changed).periods[0].margin_after_debt == -30000
    with pytest.raises(ValueError):
        prepare(c, stress(loss_source="Source inexistante"), Facts())
    changed, _, _ = prepare(c, stress(loss_source=c.periods[0].incomes[0].source), Facts())
    assert changed.periods[0].incomes[0].net.value == 0


def test_history_minimum_and_reconciliation():
    c = case()
    r = statistics(c, 3, 24)
    assert r["status"] == "available"
    assert r["mean"] == 500000
    assert r["median"] == 500000
    assert r["coefficient_of_variation"] == 0
    assert r["seasonality_profile"] is None
    f = Facts.model_validate(
        {
            "accounts": [
                {
                    "id": "A",
                    "start": "2026-01-01",
                    "end": "2026-01-31",
                    "unit_multiplier": "1000",
                    "opening": {"value": "2"},
                    "inflows": {"value": "3"},
                    "outflows": {"value": "1"},
                    "closing": {"value": "5"},
                }
            ]
        }
    )
    result = reconcile(c, f)
    assert result["checks"][0]["difference_XOF"] == 1000
    assert result["checks"][0]["status"] == "needs_verification"
    assert result["checks"][0]["scope"] == "this_account_only"


def test_grid_nonmonotone_and_no_breakpoint():
    r = search(lambda x: (x - D(".5")) ** 2 - D(".01"), D(0), D(1), 20)
    assert r["method"] == "bounded_grid"
    assert not r["monotonicity_verified_on_grid"]
    assert search(lambda x: D(1), D(0), D(1))["status"] == "not_found_in_tested_interval"


def test_illustrative_policy_and_weights(monkeypatch):
    c = case()
    p = load_policy("individuals-illustrative-v2")
    # Le produit fourni au dossier est explicitement celui de la politique de démo.
    c.analysis_details.funding.product_id = p.product.id
    assert (
        IndividualAnalysisEngine().analyze(c, p, "demonstration").scoring["qualification"]
        == "favorable"
    )
    with pytest.raises(ValueError):
        IndividualAnalysisEngine().analyze(c, p, "real")
    monkeypatch.setenv("CREDIT_ENV", "production")
    with pytest.raises(ValueError):
        IndividualAnalysisEngine().analyze(c, p, "demonstration")
    raw = p.model_dump(mode="json")
    raw["scoring_enabled"] = True
    raw["rules"][0]["weight"] = ".8"
    with pytest.raises(ValidationError):
        Policy.model_validate(raw)


def test_financing_bounded_cost_and_no_compatible_solution():
    c = case()
    p = load_policy("individuals-illustrative-v2")
    c.analysis_details.funding.product_id = p.product.id
    c.analysis_details.funding.justified_need.value = D(300000)
    r = IndividualAnalysisEngine().analyze(
        c,
        p,
        "demonstration",
        candidates=[
            Candidate(principal=300000, months=6),
            Candidate(principal=50000000, months=6),
            Candidate(principal=300000, months=12),
        ],
    )
    rows = r.deep_analysis["financing_variants"]["variants"]
    assert rows[0]["status"] == "evaluated", rows[0]
    assert rows[0]["compatible"]
    assert rows[1]["compatible"] is False
    assert rows[2]["status"] == "needs_explicit_projections"
    assert r.deep_analysis["financing_variants"]["maximum_compatible_among_tested"] == 300000
    # Source inchangée malgré le calcul de nouveaux échéanciers.
    assert c.requested_loan.principal.value == case().requested_loan.principal.value


def test_profitability_does_not_remove_liquidity_pressure():
    c = case("business_profitable_cash_tension", "businesses")
    r = BusinessAnalysisEngine().analyze(c)
    assert r.financial_risk["negative_balance_periods"]
    assert r.scoring["mandatory_review"]
    assert r.operating_state == "revue_approfondie_requise"
    assert next(s for s in r.sections if s.id == "collateral").purpose == "collateral"


def test_v2_api_history_acl_idempotency_and_pdf(client, auth_headers, monkeypatch):
    import fitz

    c = case().model_dump(mode="json")
    created = client.post("/individuals", json=c)
    assert created.status_code == 201, created.text
    path = "/individuals/" + created.json()["id"]
    opts = {
        "reverse_tests": [{"parameter": "revenue_drop", "lower": "0", "upper": ".4"}],
        "scenarios": [stress(revenue_drop=D(".2")).model_dump(mode="json")],
    }
    r = client.post(
        path + "/financial-analyses",
        json=opts,
        headers={"Idempotency-Key": "v2-control", "If-Match": "1"},
    )
    assert r.status_code == 201, r.text
    analysis = r.json()
    id = analysis["id"]
    assert analysis["engine_version"] == "financial_analysis_v2"
    assert (
        client.post(
            path + "/financial-analyses", json=opts, headers={"Idempotency-Key": "v2-control"}
        ).json()["id"]
        == id
    )
    assert (
        client.post(
            path + "/financial-analyses", json={}, headers={"Idempotency-Key": "v2-control"}
        ).status_code
        == 409
    )
    assert client.get("/assessments/" + id).json() == analysis
    assert client.get("/assessments/" + id + "/report").status_code == 200
    assert (
        client.get(
            "/financial-analyses/" + id, headers={"Authorization": "Bearer synthetic-b"}
        ).status_code
        == 403
    )
    r = client.post(
        "/financial-analyses/" + id + "/simulations",
        json=stress(revenue_drop=D(".2")).model_dump(mode="json"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["result"]["comparisons"][0]["minimum_margin_after"] == "-30000.00"
    assert client.get("/financial-analyses/" + id).json() == analysis
    edition = client.post(
        path + "/print/editions",
        json={"template_id": "analysis_report", "audience": "analyst", "assessment_id": id},
    )
    assert edition.status_code == 201, edition.text
    assert edition.json()["status"] == "completed", edition.text
    pdf = client.get("/print-editions/" + edition.json()["id"] + "/pdf")
    assert pdf.status_code == 200
    with fitz.open(stream=pdf.content, filetype="pdf") as doc:
        text = "\n".join(p.get_text() for p in doc)
    assert "Recherche bornée" in text
    assert "70/30" not in text
    old = client.post(path + "/assessments", json={})
    assert old.status_code == 201, old.text
    legacy = old.json()
    assert legacy["engine_version"] == "section-analysis-1.1.0"
    current = client.get(path).json()
    updated = current["data"]
    updated["name"] = "Nom synthétique modifié"
    assert (
        client.put(path, json=updated, headers={"If-Match": str(current["version"])}).status_code
        == 200
    )
    assert client.get("/financial-analyses/" + id).json() == analysis
    assert client.get("/assessments/" + legacy["id"]).json() == legacy
    assert client.get("/print-editions/" + edition.json()["id"] + "/pdf").content == pdf.content
    assert (
        client.post(path + "/financial-analyses", json={}, headers={"If-Match": "1"}).status_code
        == 409
    )


def test_v2_payroll_withheld_only_once(individual):
    individual["periods"][0]["incomes"][0]["net"]["value"] = "239000"
    individual["periods"][0]["payroll_loan_treatment"] = "after_loan_deductions"
    individual["periods"][0]["payroll_loan_deductions"]["value"] = "11000"
    c = CONTRACTS["individuals"].model_validate(individual)
    e = IndividualAnalysisEngine()
    assert e.calculate(c).periods[0].margin_after_debt == 67000
    changed, _, _ = prepare(c, stress(revenue_drop=D(".2")), Facts())
    assert (
        e.calculate(changed).periods[0].margin_after_debt == 17000
    )  # 250000 × .8 − 150000 − 33000.
    c.periods[0].payroll_loan_treatment = "unclear"
    assert e.analyze(c).financial_calculations["periods"][0]["margin_after_credit"] is None


def test_business_costs_fixed_variable_and_balance_units(business):
    c = CONTRACTS["businesses"].model_validate(business)
    splits = [
        {
            "period": p.period,
            "fixed": {"value": "100000"},
            "variable": {"value": str(p.operating_expenses.value - 100000)},
            "complete": True,
        }
        for p in c.periods
    ]
    facts = Facts.model_validate(
        {
            "cost_splits": splits,
            "balance_sheets": [
                {
                    "as_of": "2026-01-31",
                    "unit_multiplier": "1000",
                    "stable_resources": {"value": "100"},
                    "fixed_assets": {"value": "60"},
                    "current_assets": {"value": "80"},
                    "current_liabilities": {"value": "40"},
                }
            ],
        }
    )
    changed, _, _ = prepare(c, stress(revenue_drop=D(".2"), variable_cost_increase=D(".1")), facts)
    assert changed.periods[0].operating_expenses.value == 100000 + (
        c.periods[0].operating_expenses.value - 100000
    ) * D("1.1")
    assert changed.periods[0].receipts.value == 400000
    assert changed.periods[0].basis == "forecast"
    r = BusinessAnalysisEngine().analyze(c, facts=facts)
    metrics = {i.id: i.value for s in r.sections for i in s.indicators}
    assert metrics["working_funds_0"] == 40000
    assert metrics["current_liquidity_0"] == 2
    with pytest.raises(ValueError):
        prepare(c, stress(variable_cost_increase=D(".1")), Facts())


def test_bfr_does_not_change_direct_cashflow_and_guarantees_do_not_hide_deficit():
    c = case("business_profitable_cash_tension", "businesses")
    e = BusinessAnalysisEngine()
    before = e.calculate(c).model_dump_json()
    raw = c.model_dump(mode="json")
    raw["analysis_details"]["working_capital"]["inventory"] = {"value": "99999999"}
    raw["analysis_details"]["collateral"] = [
        {
            "description": "Garantie synthétique non vérifiée",
            "declared_value": {"value": "999999999"},
            "known_charges": {"value": "0"},
        }
    ]
    changed = CONTRACTS["businesses"].model_validate(raw)
    assert e.calculate(changed).model_dump_json() == before
    r = e.analyze(changed)
    assert r.scoring["mandatory_review"] and r.financial_risk["negative_balance_periods"]


def test_no_solution_and_term_cost():
    c = case()
    p = load_policy("individuals-illustrative-v2")
    c.analysis_details.funding.product_id = p.product.id
    r = IndividualAnalysisEngine().analyze(
        c, p, "demonstration", candidates=[Candidate(principal=50000000, months=6)]
    )
    assert r.deep_analysis["financing_variants"]["status"] == "no_compatible_solution_in_tested_set"
    r = IndividualAnalysisEngine().analyze(
        c,
        p,
        "demonstration",
        candidates=[Candidate(principal=300000, months=3), Candidate(principal=300000, months=6)],
    )
    a, b = r.deep_analysis["financing_variants"]["variants"]
    assert b["terms_after"]["first_instalment"] < a["terms_after"]["first_instalment"]
    assert b["terms_after"]["total_credit_cost"] > a["terms_after"]["total_credit_cost"]
    assert b["terms_after"]["total_repayment"] == 300000 + b["terms_after"]["total_credit_cost"]
    assert r.suggestions[-1].simulated_effect["terms_after"] == b["terms_after"]


def test_observed_negative_equity_and_seasonal_deficit():
    c = case("business_seasonal", "businesses")
    r = BusinessAnalysisEngine().analyze(c)
    assert r.financial_risk["period_deficits"]
    from credit.shared.contracts import SignedAmount

    c.analysis_details.equity = SignedAmount(value="-10000")
    # Valider le contrat après modification : les capitaux propres négatifs sont permis.
    c = CONTRACTS["businesses"].model_validate(c.model_dump(mode="json"))
    r = BusinessAnalysisEngine().analyze(c)
    section = next(s for s in r.sections if s.id == "debt")
    ratios = [i for i in section.indicators if i.id == "debt_equity"]
    assert ratios and ratios[0].value is None


def test_rate_shock_without_reviewed_clause_and_horizon():
    c = case()
    r = IndividualAnalysisEngine().analyze(
        c, scenarios=[stress(rate_increase=D(".01"), rate_contract_reference="synthetic")]
    )
    assert r.deep_analysis["scenarios"][0]["status"] == "needs_explicit_data"
    assert not r.comparisons
    with pytest.raises(ValueError):
        prepare(
            c,
            stress(delay_from=c.periods[-1].period, delay_to="2030-01-01", delay_amount=1000),
            Facts(),
        )


def test_api_different_institution_and_work_limit(client, local_identities, monkeypatch):
    import hashlib

    registry = json.loads(local_identities.read_text())
    for u in registry["users"]:
        u["institution_id"] = "institution-a"
        u["role"] = "analyst"
    registry["users"].append(
        {
            "id": "institution-b-agent",
            "token_sha256": hashlib.sha256(b"other-synthetic").hexdigest(),
            "role": "analyst",
            "institution_id": "institution-b",
            "reviewer": True,
        }
    )
    local_identities.write_text(json.dumps(registry))
    created = client.post("/individuals", json=case().model_dump(mode="json"))
    assert created.status_code == 201, created.text
    path = "/individuals/" + created.json()["id"]
    result = client.post(path + "/financial-analyses", json={})
    assert result.status_code == 201, result.text
    id = result.json()["id"]
    headers = {"Authorization": "Bearer other-synthetic"}
    assert client.get("/financial-analyses/" + id, headers=headers).status_code == 404
    assert (
        client.post(
            "/financial-analyses/" + id + "/simulations",
            json=stress().model_dump(mode="json"),
            headers=headers,
        ).status_code
        == 404
    )
    assert client.post(path + "/financial-analyses", json={}, headers=headers).status_code == 404
    monkeypatch.setenv("CREDIT_FINANCIAL_V2_MAX_WORK", "1")
    assert client.post(path + "/financial-analyses", json={}).status_code == 413


def test_approved_policy_score_orientation_and_no_renormalization():
    from credit.financial_v2.policy import qualify

    p = load_policy("individuals-illustrative-v2").model_dump(mode="json")
    p.update(
        validation_status="approved",
        approved_by="comité-synthétique",
        approved_on="2025-01-01",
        approval_reference="Décision synthétique test",
        scoring_enabled=True,
    )
    p["rules"][0]["weight"] = "1"
    policy = Policy.model_validate(p)
    r = qualify({"minimum_margin": D(70000)}, policy, [], False)
    assert r["criteria_score"] == 100 and r["risk_index"] == 0
    assert r["combined_score"] is r["probability_of_default"] is None
    r = qualify({"minimum_margin": None}, policy, [], False)
    assert r["criteria_score"] is None and r["qualification"] == "incomplet"
    r = qualify({"minimum_margin": D(-1)}, policy, [], False)
    assert r["criteria_score"] == 0 and r["mandatory_review"]
    r = qualify({"minimum_margin": D(70000)}, policy, ["Donnée critique manquante"], False)
    assert r["criteria_score"] is None


def test_policy_exception_preserves_results_and_actor(client, local_identities, monkeypatch):
    monkeypatch.setenv("CREDIT_ALLOW_DEMO", "true")
    c = case().model_dump(mode="json")
    c["analysis_details"]["funding"]["product_id"] = "unclassified"
    r = client.post("/individuals", json=c)
    assert r.status_code == 201
    path = "/individuals/" + r.json()["id"]
    r = client.post(
        path + "/financial-analyses",
        json={"mode": "demonstration", "policy_id": "individuals-illustrative-v2"},
    )
    assert r.status_code == 201, r.text
    parent = r.json()
    body = {
        "limit_ids": ["margin_nonnegative"],
        "reason": "Motif synthétique explicitement consigné",
    }
    endpoint = "/financial-analyses/" + parent["id"] + "/exceptions"
    assert client.post(endpoint, json=body).status_code == 403
    registry = json.loads(local_identities.read_text())
    registry["users"][0]["role"] = "institution_manager"
    local_identities.write_text(json.dumps(registry))
    result = client.post(endpoint, json=body)
    assert result.status_code == 201, result.text
    amended = result.json()["result"]
    assert amended["financial_calculations"] == parent["result"]["financial_calculations"]
    assert amended["scoring"] == parent["result"]["scoring"]
    assert amended["deep_analysis"]["policy_exceptions"][0]["actor_id"] == "agent-a"
    assert client.get("/financial-analyses/" + parent["id"]).json() == parent


@pytest.mark.parametrize(
    "core,name", [("individuals", "individual_control"), ("businesses", "business_seasonal")]
)
def test_more_instalment_cannot_improve_margin(core, name):
    c = case(name, core)
    engine = IndividualAnalysisEngine() if core == "individuals" else BusinessAnalysisEngine()
    before = engine.calculate(c)
    raw = c.model_dump(mode="json")
    for row in raw["requested_loan"]["schedule"]:
        row["fees"] = {"value": str(D(row["fees"]["value"]) + 1000)}
    changed = CONTRACTS[core].model_validate(raw)
    assert (
        engine.calculate(changed).periods[0].margin_after_debt
        == before.periods[0].margin_after_debt - 1000
    )


def test_extreme_unit_conversion_is_unavailable():
    f = Facts.model_validate(
        {
            "accounts": [
                {
                    "id": "A",
                    "start": "2026-01-01",
                    "end": "2026-01-31",
                    "unit_multiplier": "1000000",
                    "opening": {"value": "999999999999999999999"},
                    "closing": {"value": "1"},
                    "inflows": {"value": "0"},
                    "outflows": {"value": "0"},
                }
            ]
        }
    )
    result = reconcile(case(), f)
    assert result["checks"][0]["status"] == "incomplete"
    assert result["checks"][0]["expected_XOF"] is None
    assert any("hors limites" in m for m in result["information_requested"])


def test_applicant_v2_render_model_excludes_internal_deep_data():
    from credit.printing.presentation import build_presentation
    from credit.printing.contracts import PrintRequest

    c = case()
    report = IndividualAnalysisEngine().analyze(c).model_dump(mode="json")
    report["deep_analysis"]["facts"]["private_marker"] = "INTERNE_NE_PAS_TRANSMETTRE"
    model = build_presentation(
        c.model_dump(mode="json"),
        "individuals",
        PrintRequest(template_id="analysis_report", audience="applicant"),
        {"Dossier": "synthétique", "Édition": "test"},
        [],
        report,
        {"financial_results": True, "suggestions": True},
    )
    assert "INTERNE_NE_PAS_TRANSMETTRE" not in model.model_dump_json()
    assert "deep_analysis" not in model.model_dump_json()
    assert "Recherche bornée" not in model.model_dump_json()


def test_unknown_loan_without_schedule_never_becomes_zero():
    raw = case().model_dump(mode="json")
    raw["requested_loan"].update(
        principal={"state": "unknown", "value": None}, schedule=[], amortization_method="explicit"
    )
    c = CONTRACTS["individuals"].model_validate(raw)
    r = IndividualAnalysisEngine().analyze(c)
    assert r.financial_calculations["periods"][0]["new_debt_service"] is None
    assert r.financial_calculations["periods"][0]["margin_after_credit"] is None
    assert r.financial_risk["status"] == "incomplete"


def test_rate_shock_with_explicit_controlled_reference():
    c = case()
    raw = c.model_dump(mode="json")
    raw["evidence"][0]["status"] = "verified"
    c = CONTRACTS["individuals"].model_validate(raw)
    changed, _, _ = prepare(
        c, stress(rate_increase=D(".01"), rate_contract_reference="synthetic"), Facts()
    )
    assert sum(p.principal.value for p in changed.requested_loan.schedule) == 240000
    assert sum(p.interest.value for p in changed.requested_loan.schedule) > sum(
        p.interest.value for p in c.requested_loan.schedule
    )


def test_contribution_added_only_when_explicitly_excluded_from_opening(business):
    from credit.shared.contracts import Amount

    c = CONTRACTS["businesses"].model_validate(business)
    raw = c.model_dump(mode="json")
    raw["evidence"][0]["status"] = "verified"
    raw["data_classification"] = "synthetic"
    raw["analysis_details"]["funding"]["product_id"] = "unclassified"
    raw["analysis_details"]["funding"]["justified_need"] = {"value": "60000"}
    c = CONTRACTS["businesses"].model_validate(raw)
    p = load_policy("businesses-illustrative-v2")
    rows = (
        BusinessAnalysisEngine()
        .analyze(
            c,
            p,
            "demonstration",
            candidates=[
                Candidate(
                    principal=60000,
                    months=3,
                    contribution=Amount(value=50000),
                    contribution_evidence_ids=["synthetic"],
                    contribution_already_in_opening_cash=False,
                ),
                Candidate(
                    principal=60000,
                    months=3,
                    contribution=Amount(value=50000),
                    contribution_evidence_ids=["synthetic"],
                    contribution_already_in_opening_cash=True,
                ),
            ],
        )
        .deep_analysis["financing_variants"]["variants"]
    )
    assert D(rows[0]["input_snapshot"]["opening_cash"]["value"]) == c.opening_cash.value + 50000
    assert D(rows[1]["input_snapshot"]["opening_cash"]["value"]) == c.opening_cash.value
