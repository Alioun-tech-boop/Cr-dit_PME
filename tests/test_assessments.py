from copy import deepcopy
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest
from pydantic import ValidationError

from credit.assessment.engines import IndividualAnalysisEngine, BusinessAnalysisEngine
from credit.assessment.policy import load_policy, AssessmentPolicy
from credit.assessment.reporting import render_french
from credit.assessment.scoring import (
    ValidatedScore,
    CalibratedPD,
    LossParameter,
    Prediction,
    expected_loss,
)
from credit.assessment.simulation import SimulationSpec, prepare_simulation
from credit.businesses.contracts import BusinessCase
from credit.individuals.contracts import IndividualCase
from credit.shared.contracts import Scenario
from credit.shared.schedule import monthly_schedule

ROOT = Path("examples/assessments")


@pytest.fixture
def icase():
    return IndividualCase.model_validate_json((ROOT / "individual_control.json").read_text())


@pytest.fixture
def bcase():
    return BusinessCase.model_validate_json(
        (ROOT / "business_profitable_cash_tension.json").read_text()
    )


def policy(core):
    return load_policy(core + "-illustrative-v1", core, "demonstration", "synthetic")


def analyze(case, with_policy=True, **kwargs):
    core = "individuals" if isinstance(case, IndividualCase) else "businesses"
    engine = IndividualAnalysisEngine() if core == "individuals" else BusinessAnalysisEngine()
    return engine.analyze(case, policy(core) if with_policy else None, "demonstration", **kwargs)


def section(report, id):
    return next(s for s in report.sections if s.id == id)


def metric(section, id):
    return next(i.value for i in section.indicators if i.id == id)


def test_control_70000_and_minus_30000(icase):
    report = analyze(icase)
    assert report.financial_calculations["periods"][0]["margin_after_credit"] == "70000.00"
    stressed = IndividualAnalysisEngine().calculate(icase, Scenario(revenue_drop=D(".20")))
    assert stressed.periods[0].margin_after_credit == D(-30000)
    assert report.comparisons[0]["minimum_margin_after"] == D(-30000)
    assert report.scoring["criteria_score"] == 100
    assert report.scoring["model_status"] == "not_available"
    assert report.scoring["combined_score"] is None
    assert report.scoring["probability_of_default"] is None
    assert report.scoring["expected_loss"]["value"] is None
    assert report.lender_decision is None


@pytest.mark.parametrize(
    "id", ["identity", "income", "budget", "debt", "capacity", "reserve", "financing"]
)
def test_individual_each_section(icase, id):
    report = analyze(icase)
    item = section(report, id)
    assert item.title and item.explanation and item.data_used
    assert item.indicators
    assert item.periods
    assert item.status in {"favorable", "vigilance", "defavorable", "incomplet", "non_applicable"}
    assert all(indicator.formula and indicator.unit for indicator in item.indicators)
    assert any(data.sources for data in item.data_used)


@pytest.mark.parametrize(
    "id",
    [
        "identity",
        "activity",
        "profitability",
        "working_capital",
        "treasury",
        "debt",
        "capacity",
        "project",
        "collateral",
    ],
)
def test_business_each_section(bcase, id):
    item = section(analyze(bcase), id)
    assert item.title and item.explanation and item.indicators and item.data_used
    assert all(indicator.formula and indicator.unit for indicator in item.indicators)


def test_missing_and_non_applicable(icase, bcase):
    raw = icase.model_dump(mode="json")
    raw["periods"][0]["essential_expenses"].update(value=None, state="unknown")
    report = analyze(IndividualCase.model_validate(raw))
    assert section(report, "capacity").status == "incomplet"
    assert section(report, "capacity").score is None
    assert report.scoring["criteria_score"] is None
    assert report.financial_calculations["periods"][0]["margin_after_credit"] is None
    raw = bcase.model_dump(mode="json")
    raw["analysis_details"].update(
        working_capital=None,
        working_capital_applicable=False,
        collateral=[],
        collateral_applicable=False,
    )
    report = analyze(BusinessCase.model_validate(raw))
    assert section(report, "working_capital").status == "non_applicable"
    assert section(report, "collateral").status == "non_applicable"
    assert section(report, "collateral").score is None


def test_payroll_once_and_ambiguous(icase):
    raw = icase.model_dump(mode="json")
    raw["periods"][0]["incomes"][0]["net"]["value"] = "450000"
    raw["periods"][0]["payroll_loan_treatment"] = "after_loan_deductions"
    raw["periods"][0]["payroll_loan_deductions"]["value"] = "50000"
    case = IndividualCase.model_validate(raw)
    assert IndividualAnalysisEngine().calculate(case).periods[0].margin_after_credit == 70000
    raw["periods"][0]["payroll_loan_treatment"] = "unclear"
    report = analyze(IndividualCase.model_validate(raw))
    assert report.scoring["criteria_score"] is None
    assert any(s.id == "clarify_payroll" for s in report.suggestions)


def test_bfr_is_not_subtracted_twice(bcase):
    before = analyze(bcase)
    raw = bcase.model_dump(mode="json")
    raw["analysis_details"]["working_capital"]["receivables"]["value"] = "9000000"
    after = analyze(BusinessCase.model_validate(raw))
    assert before.financial_calculations == after.financial_calculations
    assert metric(section(before, "working_capital"), "working_capital") == D(680000)
    assert metric(section(before, "working_capital"), "dso") == D("18.60000000")


def test_profit_does_not_hide_liquidity_and_seasonal_deficit(bcase):
    report = analyze(bcase)
    assert metric(section(report, "profitability"), "net_margin") == D(".25")
    assert section(report, "treasury").status == "defavorable"
    assert report.scoring["mandatory_review"]
    assert report.financial_risk["status"] == "payment_pressure"
    seasonal = BusinessCase.model_validate_json((ROOT / "business_seasonal.json").read_text())
    report = analyze(seasonal)
    assert report.financial_risk["period_deficits"] == ["2026-02-01"]
    assert sum(
        p.operating_receipts for p in BusinessAnalysisEngine().calculate(seasonal).periods
    ) > sum(p.operating_expenses.value for p in seasonal.periods)


def test_zero_revenue_ratios_and_negative_equity(icase, bcase):
    raw = icase.model_dump(mode="json")
    raw["periods"][0]["incomes"][0]["net"]["value"] = "0"
    report = analyze(IndividualCase.model_validate(raw))
    assert report.financial_calculations["periods"][0]["debt_to_income"] is None
    assert section(report, "capacity").status == "defavorable"
    raw = bcase.model_dump(mode="json")
    raw["analysis_details"]["equity"]["value"] = "-10000"
    report = analyze(BusinessCase.model_validate(raw))
    assert metric(section(report, "debt"), "debt_equity") is None
    assert section(report, "debt").status == "defavorable"


def test_units_currency_and_comparison(bcase):
    raw = bcase.model_dump(mode="json")
    raw["analysis_details"]["accounting"][0]["currency"] = "EUR"
    with pytest.raises(ValidationError):
        BusinessCase.model_validate(raw)
    raw = bcase.model_dump(mode="json")
    raw["analysis_details"]["accounting"][0]["unit_multiplier"] = "5"
    with pytest.raises(ValidationError):
        BusinessCase.model_validate(raw)
    raw = bcase.model_dump(mode="json")
    raw["analysis_details"]["accounting"][0]["unit_multiplier"] = None
    assert section(analyze(BusinessCase.model_validate(raw)), "profitability").status == "incomplet"
    raw = bcase.model_dump(mode="json")
    raw["analysis_details"]["accounting"][0]["start"] = "2025-10-02"
    assert (
        metric(
            section(analyze(BusinessCase.model_validate(raw)), "profitability"), "turnover_growth"
        )
        is None
    )
    raw["analysis_details"]["accounting_comparison"] = "daily_rate"
    assert (
        metric(
            section(analyze(BusinessCase.model_validate(raw)), "profitability"), "turnover_growth"
        )
        is not None
    )
    raw = bcase.model_dump(mode="json")
    for item in raw["analysis_details"]["accounting"]:
        item["unit_multiplier"] = "1000"
    report = analyze(BusinessCase.model_validate(raw))
    assert metric(section(report, "profitability"), "turnover_0") == 800000000
    assert any(d.unit == "milliers_XOF" for d in section(report, "profitability").data_used)


def test_no_arbitrary_essential_cuts_and_future_expense_once(icase):
    raw = icase.model_dump(mode="json")
    raw["analysis_details"]["expenses"].append(
        {
            "period": "2026-02-01",
            "category": "health",
            "frequency": "future",
            "included_in_total": False,
            "amount": {"value": "10000", "evidence_ids": ["synthetic"]},
        }
    )
    report = analyze(IndividualCase.model_validate(raw))
    assert D(report.financial_calculations["periods"][0]["margin_after_credit"]) == 60000
    assert metric(section(report, "budget"), "essential_2026-02-01") == 310000
    assert all(
        "réduire les dépenses essentielles" not in s.action.lower() for s in report.suggestions
    )


def test_policies_weights_and_illustrative_real_forbidden(icase):
    value = policy("individuals").model_dump(mode="json")
    value["criteria"][0]["weight"] = "0.99"
    with pytest.raises(ValidationError):
        AssessmentPolicy.model_validate(value)
    value = policy("individuals").model_dump(mode="json")
    value["criteria"][1]["phenomenon"] = value["criteria"][0]["phenomenon"]
    with pytest.raises(ValidationError):
        AssessmentPolicy.model_validate(value)
    raw = icase.model_dump(mode="json")
    raw["data_classification"] = "real"
    with pytest.raises(ValueError, match="démonstration|illustrative"):
        IndividualAnalysisEngine().analyze(
            IndividualCase.model_validate(raw), policy("individuals"), "real"
        )
    report = IndividualAnalysisEngine().analyze(IndividualCase.model_validate(raw))
    assert report.scoring["criteria_score"] is None


def test_no_weight_renormalization(icase):
    raw = icase.model_dump(mode="json")
    raw["income_history"] = []
    result = analyze(IndividualCase.model_validate(raw))
    assert section(result, "income").score is None
    assert result.scoring["criteria_score"] is None
    assert result.scoring["combined_score"] is None
    trace = next(t for t in result.scoring["criteria_trace"] if t["id"] == "income_variation")
    assert trace["score"] is None and trace["weight"] == D(".20")


def test_high_other_scores_do_not_hide_deficit(icase):
    report = analyze(icase, scenario=Scenario(revenue_drop=D(".20")))
    assert section(report, "capacity").status == "defavorable"
    assert section(report, "income").score == 100
    assert report.scoring["criteria_score"] is not None
    assert report.scoring["mandatory_review"]
    assert report.operating_state == "revue_approfondie_requise"
    assert report.lender_decision is None


def approved_policy():
    value = policy("individuals").model_dump(mode="json")
    value.update(
        id="test-approved",
        validation_status="approved",
        approval={
            "authority": "Test fixture only",
            "reference": "SYNTHETIC",
            "approved_on": "2025-01-01",
        },
        allow_model=True,
        model_populations=["test-population"],
        model_required_fields=["periods.*.incomes.*.net"],
    )
    return AssessmentPolicy.model_validate(value)


def prediction(**overrides):
    score = ValidatedScore(
        value=80,
        validated=True,
        validation_reference="synthetic-model-test",
        validation_date=date(2025, 1, 1),
        model_version="fake-fixture-v1",
        profile="employee",
        product_id="demo-monthly",
        population="test-population",
        required_data_complete=True,
    )
    return Prediction(score=score.model_copy(update=overrides))


class FakeAdapter:
    def __init__(self, result):
        self.result = result

    def predict(self, features):
        return self.result


def test_dual_compatible_and_no_pd_from_score(icase):
    report = IndividualAnalysisEngine().analyze(
        icase,
        approved_policy(),
        "real",
        stress_scenarios=[Scenario(revenue_drop=D(".2"))],
        model=FakeAdapter(prediction()),
    )
    assert report.scoring["combined_score"] == D(94)
    assert report.scoring["risk_index"] == D(6)
    assert report.scoring["probability_of_default"] is None
    assert report.scoring["expected_loss"]["value"] is None


@pytest.mark.parametrize(
    "changes",
    [
        {"scale": "other"},
        {"orientation": "higher_is_riskier"},
        {"profile": "retired"},
        {"product_id": "other"},
        {"population": "other"},
        {"validated": False},
        {"required_data_complete": False},
        {"validation_date": date(2027, 1, 1)},
    ],
)
def test_incompatible_dual_remains_null(icase, changes):
    result = IndividualAnalysisEngine().analyze(
        icase,
        approved_policy(),
        "real",
        stress_scenarios=[Scenario(revenue_drop=D(".2"))],
        model=FakeAdapter(prediction(**changes)),
    )
    assert result.scoring["criteria_score"] == 100
    assert result.scoring["combined_score"] is None
    assert result.scoring["probability_of_default"] is None


def test_expected_loss_requires_justified_compatible_parameters():
    pd = CalibratedPD(
        value=D(".1"),
        calibrated=True,
        required_data_complete=True,
        validated=True,
        default_definition="Synthetic definition only",
        horizon_months=12,
        population="test",
        profile="employee",
        product_id="demo-monthly",
        model_version="fixture",
        validation_date=date(2025, 1, 1),
        validation_reference="PD-synthetic",
    )
    common = {
        "justified": True,
        "reference": "SYNTHETIC",
        "horizon_months": 12,
        "population": "test",
        "profile": "employee",
        "product_id": "demo-monthly",
    }
    lgd = LossParameter(kind="LGD", value=D(".4"), unit="fraction", **common)
    ead = LossParameter(kind="EAD", value=D("100000"), unit="XOF", **common)
    assert expected_loss(pd, lgd, ead)["value"] == 4000
    assert expected_loss(pd, lgd.model_copy(update={"horizon_months": 6}), ead)["value"] is None
    assert expected_loss(pd.model_copy(update={"calibrated": False}), lgd, ead)["value"] is None
    assert expected_loss(None, lgd, ead)["value"] is None


def test_lower_amount_and_term_cost_original_immutable(icase):
    before = icase.model_dump(mode="json")
    engine = IndividualAnalysisEngine()
    change = prepare_simulation(
        icase, SimulationSpec(kind="lower_amount", principal=D(192000)), policy("individuals")
    )
    assert change["status"] == "available"
    after = engine.calculate(change["case"])
    assert after.periods[0].margin_after_credit == 86000
    assert icase.model_dump(mode="json") == before
    raw = deepcopy(before)
    loan = monthly_schedule(D(240000), D(".12"), 3, date(2026, 2, 1), D(1000)).model_copy(
        update={"reference": "requested", "amortization_method": "monthly_constant"}
    )
    raw["requested_loan"] = loan.model_dump(mode="json")
    case = IndividualCase.model_validate(raw)
    change = prepare_simulation(
        case, SimulationSpec(kind="extend_term", months=6), policy("individuals")
    )
    assert (
        change["terms"]["after"]["first_instalment"] < change["terms"]["before"]["first_instalment"]
    )
    assert (
        change["terms"]["after"]["total_credit_cost"]
        > change["terms"]["before"]["total_credit_cost"]
    )
    assert change["terms"]["after"]["total_repayment"] == sum(
        p.principal.value + p.interest.value + p.fees.value
        for p in change["case"].requested_loan.schedule
    )
    with pytest.raises(ValueError):
        prepare_simulation(
            case, SimulationSpec(kind="extend_term", months=37), policy("individuals")
        )


def test_extension_without_projections_cannot_fabricate_revenue(icase):
    change = prepare_simulation(
        icase, SimulationSpec(kind="extend_term", months=12), policy("individuals")
    )
    assert change["case"] is None
    assert change["status"] == "needs_explicit_projections"
    assert change["terms"]["after"]["total_repayment"] == 240000
    assert change["missing_information"]


def test_suggestions_quantified_and_contribution_gap(icase):
    raw = icase.model_dump(mode="json")
    raw["periods"][0]["incomes"][0]["net"]["value"] = "400000"
    raw["analysis_details"]["funding"]["verified_contribution"]["value"] = "0"
    report = analyze(IndividualCase.model_validate(raw))
    lower = next(s for s in report.suggestions if s.id == "lower_amount")
    assert lower.simulated_effect["financial_comparison"]["minimum_margin_before"] == -30000
    assert lower.simulated_effect["financial_comparison"]["minimum_margin_after"] == -14000
    contribution = next(s for s in report.suggestions if s.id == "contribution_gap")
    assert contribution.simulated_effect["additional_verified_contribution_needed"] == 24000
    assert contribution.simulated_effect["availability_assumed"] is False


def test_startup_delay_moves_only_project_receipts(bcase):
    before = bcase.model_dump(mode="json")
    prepared = prepare_simulation(
        bcase, SimulationSpec(kind="startup_delay", startup_delay_periods=1), policy("businesses")
    )
    case = prepared["case"]
    assert case.periods[0].receipts.value == 50000
    assert case.periods[1].receipts.value == 550000
    assert sum(p.receipts.value for p in case.periods) == sum(
        p.receipts.value for p in bcase.periods
    )
    assert bcase.model_dump(mode="json") == before


def test_intraperiod_deficit_not_hidden_by_month_end(icase):
    raw = icase.model_dump(mode="json")
    raw["mobilizable_reserve"]["value"] = "0"
    flows = []
    for p in icase.periods:
        month = p.period.month
        flows.extend(
            [
                {
                    "period": p.period.isoformat(),
                    "date": f"2026-{month:02d}-28",
                    "kind": "income",
                    "amount": {"value": "500000"},
                },
                {
                    "period": p.period.isoformat(),
                    "date": f"2026-{month:02d}-05",
                    "kind": "essential",
                    "amount": {"value": "300000"},
                },
            ]
        )
    raw["analysis_details"].update(timing_complete=True, dated_flows=flows)
    report = analyze(IndividualCase.model_validate(raw))
    assert report.financial_calculations["periods"][0]["margin_after_credit"] == "70000.00"
    assert report.financial_risk["dated_cashflow_analysis"]["minimum_balance"] < 0
    assert report.scoring["mandatory_review"]
    assert section(report, "reserve").status == "defavorable"


def test_deterministic_report_and_raw_ocr_blocked(icase):
    before = icase.model_dump(mode="json")
    assert analyze(icase).model_dump_json() == analyze(icase).model_dump_json()
    assert icase.model_dump(mode="json") == before
    raw = deepcopy(before)
    raw["evidence"][0]["status"] = "unverified_extracted"
    report = analyze(IndividualCase.model_validate(raw))
    assert report.financial_calculations["periods"][0]["margin_after_credit"] is None
    assert report.scoring["criteria_score"] is None
    assert section(report, "identity").status == "incomplet"
    assert "fraude" not in " ".join(report.major_alerts).lower()
    assert "Ce rapport n’est pas un accord bancaire" in render_french(report)


def test_independent_section_analyzers(icase, bcase):
    from credit.assessment.context import AnalysisContext
    from credit.individuals.sections import income
    from credit.businesses.sections import profitability

    first = AnalysisContext(icase, IndividualAnalysisEngine().calculate(icase))
    assert metric(income(first), "history_cv") == 0
    second = AnalysisContext(bcase, BusinessAnalysisEngine().calculate(bcase))
    assert metric(profitability(second), "net_margin") == D(".25")


def test_validated_calibrated_pd_is_separate_and_scope_checked(icase):
    pd = CalibratedPD(
        value=D(".03"),
        calibrated=True,
        validated=True,
        required_data_complete=True,
        default_definition="Définition synthétique propre au test, aucune norme proposée",
        horizon_months=12,
        population="test-population",
        profile="employee",
        product_id="demo-monthly",
        model_version="fake-fixture-v1",
        validation_date=date(2025, 1, 1),
        validation_reference="SYNTHETIC",
    )
    supplied = prediction().model_copy(update={"pd": pd})
    report = IndividualAnalysisEngine().analyze(
        icase,
        approved_policy(),
        "real",
        stress_scenarios=[Scenario(revenue_drop=D(".2"))],
        model=FakeAdapter(supplied),
    )
    assert report.scoring["combined_score"] == 94
    assert report.scoring["probability_of_default"]["value"] == "0.03"
    assert (
        D(report.scoring["probability_of_default"]["value"]) != report.scoring["risk_index"] / 100
    )
    supplied = supplied.model_copy(update={"pd": pd.model_copy(update={"profile": "retired"})})
    report = IndividualAnalysisEngine().analyze(
        icase,
        approved_policy(),
        "real",
        stress_scenarios=[Scenario(revenue_drop=D(".2"))],
        model=FakeAdapter(supplied),
    )
    assert report.scoring["combined_score"] == 94
    assert report.scoring["probability_of_default"] is None


def test_explicit_future_projections_and_client_delay(icase, bcase):
    future = []
    for day in ["2026-08-01", "2026-09-01", "2026-10-01", "2026-11-01", "2026-12-01", "2027-01-01"]:
        item = icase.periods[-1].model_dump(mode="json")
        item["period"] = day
        item["incomes"][0]["net"]["value"] = "450000"
        future.append(item)
    spec = SimulationSpec(
        kind="extend_term",
        months=12,
        future_periods=future,
        projection_assumptions=[
            "Revenus futurs de 450000 fournis explicitement, hors moyenne historique."
        ],
    )
    prepared = prepare_simulation(icase, spec, policy("individuals"))
    assert prepared["status"] == "available"
    assert (
        IndividualAnalysisEngine().calculate(prepared["case"]).periods[-1].net_retained_income
        == 450000
    )
    before = BusinessAnalysisEngine().calculate(bcase)
    after = BusinessAnalysisEngine().calculate(
        bcase,
        Scenario(delay_from=date(2026, 3, 1), delay_to=date(2026, 4, 1), delay_amount=D(100000)),
    )
    assert after.periods[1].closing_cash == before.periods[1].closing_cash - 100000
    assert after.periods[-1].closing_cash == before.periods[-1].closing_cash


def test_collateral_does_not_repair_coverage_and_dso_missing_denominator(bcase):
    before = analyze(bcase)
    raw = bcase.model_dump(mode="json")
    raw["analysis_details"]["collateral"][0]["declared_value"]["value"] = "100000000"
    raw["analysis_details"]["working_capital"]["credit_sales"] = None
    after = analyze(BusinessCase.model_validate(raw))
    assert metric(section(after, "capacity"), "minimum_coverage") == metric(
        section(before, "capacity"), "minimum_coverage"
    )
    assert after.scoring["criteria_score"] == before.scoring["criteria_score"]
    assert metric(section(after, "working_capital"), "dso") is None
    assert after.financial_risk["status"] == "payment_pressure"


def test_documentary_issue_is_not_financial_default(icase):
    raw = icase.model_dump(mode="json")
    raw["analysis_details"]["identity"]["subject_linked"] = None
    report = analyze(IndividualCase.model_validate(raw))
    assert section(report, "identity").status == "incomplet"
    assert section(report, "capacity").status == "favorable"
    assert report.scoring["criteria_score"] == 100
    assert report.scoring["mandatory_review"]


def test_calendar_and_documented_restructuring_are_explicit(icase):
    from credit.shared.contracts import Payment

    raw = icase.model_dump(mode="json")
    calendar = []
    for value in raw["requested_loan"]["schedule"]:
        row = deepcopy(value)
        row["due_date"] = row["period"][:8] + "15"
        calendar.append(Payment.model_validate(row))
    prepared = prepare_simulation(
        icase, SimulationSpec(kind="calendar", schedule=calendar), policy("individuals")
    )
    assert prepared["case"].requested_loan.schedule[0].due_date.day == 15
    assert prepared["case"].requested_loan.principal.value == 240000
    old_schedule = [Payment.model_validate(p) for p in raw["existing_loans"][0]["schedule"]]
    with pytest.raises(ValueError, match="documenté"):
        prepare_simulation(
            icase,
            SimulationSpec(
                kind="existing_restructure", schedule=old_schedule, existing_reference="existing"
            ),
            policy("individuals"),
        )
    assert (
        prepare_simulation(
            icase,
            SimulationSpec(
                kind="existing_restructure",
                schedule=old_schedule,
                existing_reference="existing",
                documented_schedule_evidence_ids=["synthetic"],
            ),
            policy("individuals"),
        )["status"]
        == "available"
    )
    restricted = policy("individuals").model_copy(deep=True)
    restricted.product.allowed_due_days = [1]
    with pytest.raises(ValueError, match="autorisé"):
        prepare_simulation(icase, SimulationSpec(kind="calendar", schedule=calendar), restricted)


def test_missing_history_is_not_good_payer_and_forecast_is_explicit(icase):
    raw = icase.model_dump(mode="json")
    raw["analysis_details"].update(repayment_history_applicable=None, repayment_observations=[])
    report = analyze(IndividualCase.model_validate(raw))
    assert section(report, "debt").status == "incomplet"
    assert any("historique" in value for value in section(report, "debt").missing_information)
    assert any("prévisionnels" in value for value in report.assumptions)


def test_review_only_model_data_and_fixed_legacy_combination(icase):
    from credit.shared.scoring import CombinationPolicy

    with pytest.raises(ValidationError):
        CombinationPolicy(criteria_weight=D(".8"), model_weight=D(".2"))

    class Unavailable:
        def predict(self, features):
            raise RuntimeError("Synthetic unavailable provider")

    result = IndividualAnalysisEngine().analyze(
        icase,
        approved_policy(),
        "real",
        stress_scenarios=[Scenario(revenue_drop=D(".2"))],
        model=Unavailable(),
    )
    assert result.scoring["model_status"] == "not_available"
    assert result.scoring["criteria_score"] == 100
    assert result.scoring["combined_score"] is None


def test_observed_future_is_not_certain_and_projection_is_not_extended(icase, bcase):
    raw = icase.model_dump(mode="json")
    raw["periods"][0]["basis"] = "observed"
    with pytest.raises(ValidationError, match="prévision"):
        IndividualCase.model_validate(raw)
    raw = bcase.model_dump(mode="json")
    raw["analysis_details"]["accounting"][-1]["end"] = "2026-12-31"
    with pytest.raises(ValidationError, match="observé"):
        BusinessCase.model_validate(raw)


def test_suggestion_preserves_active_stress(icase):
    report = analyze(icase, scenario=Scenario(revenue_drop=D(".20")))
    lower = next(s for s in report.suggestions if s.id == "lower_amount")
    assert lower.simulated_effect["financial_comparison"]["minimum_margin_before"] == -30000
    assert lower.simulated_effect["financial_comparison"]["minimum_margin_after"] == -14000
