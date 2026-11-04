from copy import deepcopy
from datetime import date
from decimal import Decimal as D

import pytest
from pydantic import ValidationError

from credit.businesses.contracts import BusinessCase
from credit.businesses.engine import analyze as business_analyze
from credit.individuals.contracts import IndividualCase
from credit.individuals.engine import analyze
from credit.shared.contracts import Amount, Scenario
from credit.shared.schedule import monthly_schedule
from credit.shared.scoring import CombinationPolicy, Score


def test_individual_nominal(individual):
    result = analyze(IndividualCase.model_validate(individual))
    assert result.status == "complete"
    assert result.periods[0].available_before_debt == D(100000)
    assert result.periods[0].margin_after_debt == D(67000)
    assert result.periods[0].debt_to_income == D("0.132")
    assert result.periods[-1].closing_reserve_or_cash == D(304000)
    assert result.scoring.model_status == "not_available"
    assert result.scoring.combined_score is None
    assert result.recommendation is None and result.lender_decision is None


def test_business_nominal_and_financing(business):
    result = business_analyze(BusinessCase.model_validate(business))
    row = result.periods[0]
    assert row.cash_available_for_debt == D(270000)
    assert row.margin_after_debt == D(237000)
    assert row.closing_reserve_or_cash == D(337000)
    assert row.financing_received == row.financed_uses == D(60000)
    assert row.debt_service_coverage == D(270000) / D(33000)
    business["periods"][0]["financed_uses"]["value"] = "0"
    assert business_analyze(BusinessCase.model_validate(business)).periods[
        0
    ].closing_reserve_or_cash == D(397000)


@pytest.mark.parametrize("field", ["essential_expenses", "payroll_loan_deductions"])
def test_unknown(individual, field):
    individual["periods"][0][field] = {"value": None, "state": "unknown"}
    individual["periods"][0]["payroll_loan_treatment"] = "after_loan_deductions"
    result = analyze(IndividualCase.model_validate(individual))
    assert result.status == "incomplete"
    assert result.periods[0].margin_after_debt is None
    assert result.periods[-1].closing_reserve_or_cash is None
    assert result.information_requested


def test_business_unknown(business):
    business["periods"][0]["receipts"] = {"value": None, "state": "unknown"}
    result = business_analyze(BusinessCase.model_validate(business))
    assert result.status == "incomplete"
    assert result.periods[0].debt_service_coverage is None
    assert result.financial_findings.minimum_balance is None


@pytest.mark.parametrize("value", ["-1", "0.001", "NaN", "Infinity"])
def test_invalid_amount(value):
    with pytest.raises(ValidationError):
        Amount(value=value)


def test_invalid_period(individual):
    individual["periods"][1]["period"] = individual["periods"][0]["period"]
    with pytest.raises(ValidationError):
        IndividualCase.model_validate(individual)


def test_zero_income(individual):
    individual["periods"][0]["incomes"][0]["net"]["value"] = "0"
    result = analyze(IndividualCase.model_validate(individual))
    assert result.periods[0].debt_to_income is None
    assert result.periods[0].margin_after_debt == D(-183000)
    assert result.financial_findings.deficit_periods == [date(2026, 2, 1)]


def test_zero_debt(business):
    business["existing_loans"] = []
    result = business_analyze(BusinessCase.model_validate(business))
    assert result.periods[1].debt_service_coverage is None


@pytest.mark.parametrize("rate", [D(0), D("0.12"), D("0.075")])
def test_schedule(rate):
    loan = monthly_schedule(D(100000), rate, 12, date(2026, 1, 31), D(100))
    assert sum(p.principal.value for p in loan.schedule) == D(100000)
    assert loan.schedule[1].period == date(2026, 2, 28)
    assert loan.schedule[2].period == date(2026, 3, 31)
    assert all(p.fees.value == D(100) for p in loan.schedule)
    if not rate:
        assert loan.schedule[-1].principal.value == D("8333.37")
        assert sum(p.interest.value for p in loan.schedule) == 0


def test_irregular_schedule(individual):
    result = analyze(IndividualCase.model_validate(individual))
    assert [r.new_debt_service for r in result.periods] == [D(22000), D(0), D(42000)]


def test_duplicate_debt(individual):
    individual["existing_loans"].append(deepcopy(individual["existing_loans"][0]))
    with pytest.raises(ValidationError):
        IndividualCase.model_validate(individual)


def test_payroll_deduction_once(individual):
    individual["periods"][0]["incomes"][0]["net"]["value"] = "239000"
    individual["periods"][0]["payroll_loan_treatment"] = "after_loan_deductions"
    individual["periods"][0]["payroll_loan_deductions"]["value"] = "11000"
    assert analyze(IndividualCase.model_validate(individual)).periods[0].margin_after_debt == D(
        67000
    )
    individual["periods"][0]["payroll_loan_treatment"] = "unclear"
    assert analyze(IndividualCase.model_validate(individual)).status == "incomplete"


def test_self_employed_net(individual):
    income = individual["periods"][0]["incomes"][0]
    income["kind"] = "self_employed_net"
    result = analyze(IndividualCase.model_validate(individual))
    assert result.status == "incomplete"
    assert result.periods[0].net_retained_income is None


def test_household_once(business):
    business["periods"][0]["operating_expenses"]["value"] = "220000"
    business["periods"][0]["household_included_in_operating"] = True
    result = business_analyze(BusinessCase.model_validate(business))
    assert result.periods[0].margin_after_debt == D(237000)


def test_stress(individual, business):
    scenario = Scenario(revenue_drop=D("0.2"), expense_increase=D("0.1"))
    result = analyze(IndividualCase.model_validate(individual), scenario)
    assert result.periods[0].margin_after_debt == D(2000)
    assert result.assumptions["scenario"]["revenue_drop"] == "0.2"
    row = business_analyze(BusinessCase.model_validate(business), scenario).periods[0]
    assert row.margin_after_debt == D(117000)


def test_delay(business):
    base = BusinessCase.model_validate(business)
    scenario = Scenario(
        delay_from=date(2026, 2, 1), delay_to=date(2026, 3, 1), delay_amount=D(100000)
    )
    result = business_analyze(base, scenario)
    assert result.periods[0].operating_receipts == D(400000)
    assert result.periods[1].operating_receipts == D(600000)
    assert (
        result.periods[-1].closing_reserve_or_cash
        == business_analyze(base).periods[-1].closing_reserve_or_cash
    )
    with pytest.raises(ValueError):
        business_analyze(
            base,
            Scenario(delay_from=date(2026, 2, 1), delay_to=date(2027, 2, 1), delay_amount=D(1)),
        )


def test_evidence_and_currency(individual):
    individual["evidence"][0]["status"] = "contradictory"
    assert analyze(IndividualCase.model_validate(individual)).status == "incomplete"
    individual["evidence"][0]["currency"] = "EUR"
    with pytest.raises(ValidationError):
        IndividualCase.model_validate(individual)


def test_no_fictional_score():
    policy = CombinationPolicy()
    score = Score(value=80, scale="grid-v1", validation_version="v1", usable=True)
    assert policy.combine(score, None) is None
    other = score.model_copy(update={"scale": "different"})
    assert policy.combine(score, other) is None
    assert policy.combine(score, score) == 80


def test_no_raw_transactions(business):
    # Aucun import de transactions : transferts internes exclus des agrégats en amont.
    business["transactions"] = [{"kind": "internal_transfer", "amount": 100}]
    with pytest.raises(ValidationError):
        BusinessCase.model_validate(business)


def test_variability_uses_history_only(individual):
    base = IndividualCase.model_validate(individual)
    assert analyze(base).financial_findings.income_variability_cv is None
    individual["income_history"] = [
        {"period": f"2025-{month:02}-01", "net_personal_income": {"value": str(value)}}
        for month, value in [(10, 100), (11, 200), (12, 300)]
    ]
    cv = analyze(IndividualCase.model_validate(individual)).financial_findings.income_variability_cv
    assert cv.quantize(D("0.0001")) == D("0.4082")


def test_missing_vs_not_applicable(individual):
    individual["periods"][0]["essential_expenses"] = {"value": None, "state": "not_applicable"}
    assert analyze(IndividualCase.model_validate(individual)).status == "incomplete"
    with pytest.raises(ValidationError):
        Amount(value=0, state="unknown")


def test_schedule_principal_consistency(individual):
    individual["requested_loan"]["principal"]["value"] = "70000"
    with pytest.raises(ValidationError):
        IndividualCase.model_validate(individual)


def test_financing_consistency(business):
    business["periods"][0]["requested_loan_disbursement"]["value"] = "70000"
    with pytest.raises(ValidationError):
        BusinessCase.model_validate(business)


def test_unknown_capital(individual):
    individual["requested_loan"]["principal"] = {"value": None, "state": "unknown"}
    result = analyze(IndividualCase.model_validate(individual))
    assert result.status == "incomplete"
    assert "capital/requested" in result.information_requested


def test_self_employed_reconciled_calculation(individual):
    income = individual["periods"][0]["incomes"][0]
    income.update(
        kind="self_employed_net",
        activity_receipts={"value": "400000"},
        necessary_professional_costs={"value": "150000"},
    )
    assert analyze(IndividualCase.model_validate(individual)).periods[0].net_retained_income == D(
        250000
    )
    income["necessary_professional_costs"]["value"] = "100000"
    assert analyze(IndividualCase.model_validate(individual)).status == "incomplete"
