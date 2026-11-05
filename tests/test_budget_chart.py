"""Résultats attendus explicites ; aucune donnée réelle dans les fixtures."""

from copy import deepcopy
from decimal import Decimal
import pytest
from credit.web.budget import budget_chart


def report(core="individuals", income="500000", available="200000", margin="70000"):
    row = {"period": "2026-12-01", "existing_debt_service": "50000", "new_debt_service": "80000"}
    row.update(
        {
            "operating_receipts" if core == "businesses" else "net_retained_income": income,
            "cash_available_for_debt"
            if core == "businesses"
            else "available_before_debt": available,
            "margin_after_debt" if core == "businesses" else "margin_after_credit": margin,
            "closing_cash" if core == "businesses" else "projected_reserve": "170000",
        }
    )
    return {
        "core": core,
        "engine_version": "test-engine",
        "financial_calculations": {"periods": [row]},
    }


def project(data):
    return budget_chart(
        data,
        {
            "periods": [{"period": "2026-12-01", "basis": "forecast"}],
            "mobilizable_reserve": {"value": "100000", "state": "known"},
            "opening_cash": {"value": "100000", "state": "known"},
        },
        case_id="case-synthetic",
        assessment_id="analysis-synthetic",
    )


def test_reference_personal_budget_and_immutable_source():
    original = report()
    before = deepcopy(original)
    chart = project(original)
    row = chart["periods"][0]
    assert row["capacity"]["value"] == "70000.00"
    assert row["capacity"]["total"] == "200000.00"
    assert row["debt"]["value"] == "130000.00"
    assert [x["percentage"] for x in row["capacity"]["segments"]] == [
        "25.0000",
        "40.0000",
        "35.0000",
    ]
    assert row["liquidity"]["value"] == "170000.00"
    assert [x["value"] for x in row["liquidity"]["segments"]] == ["100000.00", "70000.00"]
    assert row["basis"] == "forecast" and chart["currency"] == "XOF"
    assert original == before


def test_deficit_is_visible_without_negative_donut_slice():
    row = project(report(income="400000", available="100000", margin="-30000"))["periods"][0]
    assert row["deficit"] is True
    assert row["capacity"]["value"] == "-30000.00"
    assert row["capacity"]["total"] == "130000.00"
    assert all(Decimal(x["value"]) >= 0 for x in row["capacity"]["segments"])
    assert not any(x["id"] == "remaining" for x in row["capacity"]["segments"])


def test_business_financing_and_working_capital_not_counted_as_income_or_expense():
    r = report("businesses", "4000000", "1000000", "350000")
    p = r["financial_calculations"]["periods"][0]
    p.update(
        existing_debt_service="250000",
        new_debt_service="400000",
        financing_received="2000000",
        financed_uses="2000000",
        working_capital_change="500000",
    )
    row = project(r)["periods"][0]
    assert row["debt"]["value"] == "650000.00"
    assert row["capacity"]["value"] == "350000.00"
    assert row["capacity"]["total"] == "1000000.00"


@pytest.mark.parametrize(
    "missing",
    ["existing_debt_service", "new_debt_service", "margin_after_credit"],
)
def test_unknown_is_not_zero_or_a_complete_chart(missing):
    r = report()
    r["financial_calculations"]["periods"][0][missing] = None
    row = project(r)["periods"][0]
    assert row["capacity"]["total"] is None
    assert row["capacity"]["status"] == "incomplete"
    assert all(x["percentage"] is None for x in row["capacity"]["segments"])


def test_zero_and_zero_denominator_are_distinct_from_unknown():
    r = report(income="0", available="0", margin="0")
    r["financial_calculations"]["periods"][0].update(
        existing_debt_service="0", new_debt_service="0"
    )
    row = project(r)["periods"][0]
    assert row["debt"]["value"] == row["capacity"]["value"] == "0.00"
    assert row["capacity"]["status"] == "zero"
    assert all(x["percentage"] is None for x in row["capacity"]["segments"])


def test_missing_margin_is_incomplete_even_with_known_expenses():
    row = project(report(margin=None))["periods"][0]
    assert row["capacity"]["value"] is None
    assert row["capacity"]["status"] == "incomplete"


def test_exact_decimal_and_snapshot_basis():
    r = report(
        income="9007199254740993.99", available="9007199254740993.98", margin="9007199254740993.98"
    )
    r["financial_calculations"]["periods"][0].update(
        existing_debt_service="0", new_debt_service="0"
    )
    row = project(r)["periods"][0]
    assert row["capacity"]["value"] == "9007199254740993.98"
    assert row["capacity"]["total"] == "9007199254740993.98"


def test_no_result_no_fabricated_period():
    r = report()
    r["financial_calculations"]["periods"] = []
    assert project(r)["periods"] == []


@pytest.mark.parametrize(
    "balance,expected,negative",
    [
        ("60000", ["60000.00", "40000.00"], False),
        ("-30000", ["100000.00", "30000.00"], True),
        ("0", ["0.00", "100000.00"], False),
    ],
)
def test_liquidity_decrease_shortfall_and_zero(balance, expected, negative):
    r = report()
    r["financial_calculations"]["periods"][0]["projected_reserve"] = balance
    view = project(r)["periods"][0]["liquidity"]
    assert view["value"] == format(Decimal(balance), ".2f")
    assert [s["value"] for s in view["segments"]] == expected
    assert view["negative"] is negative
    assert all(Decimal(s["value"]) >= 0 for s in view["segments"])


def test_unknown_initial_reserve_does_not_fabricate_coverage():
    chart = budget_chart(
        report(),
        {"mobilizable_reserve": {"state": "unknown", "value": None}},
        case_id="case-synthetic",
        assessment_id="analysis-synthetic",
    )
    view = chart["periods"][0]["liquidity"]
    assert view["status"] == "incomplete"
    assert all(s["percentage"] is None for s in view["segments"])
