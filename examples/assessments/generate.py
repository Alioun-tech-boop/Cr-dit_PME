"""Dossiers et rapports exclusivement synthétiques du moteur par sections."""

from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from credit.shared.schedule import monthly_schedule
from credit.individuals.contracts import IndividualCase
from credit.businesses.contracts import BusinessCase
from credit.assessment.engines import IndividualAnalysisEngine, BusinessAnalysisEngine
from credit.assessment.policy import load_policy
from credit.assessment.reporting import render_french
from decimal import Decimal

ROOT = Path(__file__).parent


def amount(value):
    return {"value": str(value), "state": "known", "evidence_ids": ["synthetic"]}


def note(text):
    return {"text": text, "evidence_ids": ["synthetic"]}


def save(name, data):
    (ROOT / (name + ".json")).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


individual = json.loads(Path("examples/salarie.json").read_text())
individual.update(
    name="Cas de contrôle synthétique 500000 / 300000 / 50000 / 80000",
    data_classification="synthetic",
)
loan = monthly_schedule(Decimal(240000), Decimal(0), 3, date(2026, 2, 1)).model_copy(
    update={"reference": "requested", "amortization_method": "monthly_constant"}
)
individual["requested_loan"] = loan.model_dump(mode="json")
for p in individual["requested_loan"]["schedule"]:
    for k in ["principal", "interest", "fees"]:
        p[k]["evidence_ids"] = ["synthetic"]
individual["requested_loan"]["principal"]["evidence_ids"] = ["synthetic"]
existing = monthly_schedule(Decimal(150000), Decimal(0), 3, date(2026, 2, 1)).model_copy(
    update={"reference": "existing"}
)
individual["existing_loans"] = [existing.model_dump(mode="json")]
for p in individual["existing_loans"][0]["schedule"]:
    for k in ["principal", "interest", "fees"]:
        p[k]["evidence_ids"] = ["synthetic"]
individual["existing_loans"][0]["principal"]["evidence_ids"] = ["synthetic"]
base = deepcopy(individual["periods"][0])
base["incomes"][0]["net"] = amount(500000)
base["essential_expenses"] = amount(300000)
individual["periods"] = [
    {**deepcopy(base), "period": f"2026-{month:02d}-01", "basis": "forecast"}
    for month in range(2, 8)
]
individual["mobilizable_reserve"] = amount(1000000)
individual["income_history"] = [
    {"period": day, "net_personal_income": amount(500000)}
    for day in ["2025-11-01", "2025-12-01", "2026-01-01"]
]
individual["analysis_details"] = {
    "as_of": "2026-01-31",
    "identity": {
        "subject_linked": True,
        "household_confirmed": True,
        "evidence_ids": ["synthetic"],
    },
    "funding": {
        "product_id": "demo-monthly",
        "justified_need": amount(240000),
        "announced_contribution": amount(24000),
        "verified_contribution": amount(24000),
        "purpose": note("Besoin synthétique justifié ; réserve fournie hors apport affecté."),
    },
    "repayment_history_applicable": True,
    "repayment_observations": [
        {
            "loan_reference": "existing",
            "as_of": "2026-01-31",
            "arrears": amount(0),
            "days_past_due": 0,
            "restructuring_count": 0,
        }
    ],
    "continuity": [
        note(
            "Contrat synthétique et revenus prévisionnels explicitement déclarés ; pas une garantie."
        )
    ],
    "expense_breakdown_complete": True,
    "expenses": [
        {
            "period": f"2026-{m:02d}-01",
            "category": category,
            "frequency": "recurring",
            "amount": amount(value),
            "included_in_total": True,
        }
        for m in range(2, 8)
        for category, value in [("housing", 150000), ("food", 100000), ("transport", 50000)]
    ],
    "blocked_savings": amount(0),
    "projection_assumptions": [
        note(
            "Six mois de flux fournis séparément ; aucune extrapolation automatique par le moteur."
        )
    ],
}
save("individual_control", individual)
incomplete = deepcopy(individual)
incomplete["name"] = "Dossier synthétique incomplet : dépenses et montant de réserve inconnus"
incomplete["periods"][0]["essential_expenses"] = {
    "state": "unknown",
    "value": None,
    "evidence_ids": ["synthetic"],
}
incomplete["mobilizable_reserve"] = {
    "state": "unknown",
    "value": None,
    "evidence_ids": ["synthetic"],
}
save("individual_incomplete", incomplete)

business = json.loads(Path("examples/pme_structuree.json").read_text())
business.update(
    name="Entreprise synthétique rentable, mais sous tension de trésorerie",
    data_classification="synthetic",
)
business["periods"][0]["receipts"] = amount(100000)
business["opening_cash"] = amount(10000)
business["historical_cashflows"] = [
    {
        **deepcopy(business["periods"][1]),
        "period": f"2025-{m:02d}-01",
        "basis": "observed",
        "receipts": amount(value),
    }
    for m, value in [(10, 200000), (11, 600000), (12, 100000)]
]
accounting = []
for start, end, revenue, profit in [
    ("2025-10-01", "2025-10-31", 800000, 200000),
    ("2025-12-01", "2025-12-31", 1000000, 250000),
]:
    accounting.append(
        {
            "start": start,
            "end": end,
            "currency": "XOF",
            "unit_multiplier": "1",
            "turnover": amount(revenue),
            "cost_of_sales": amount(revenue // 2),
            "operating_expenses": amount(revenue // 4),
            "operating_result": amount(profit),
            "net_result": amount(profit),
            "equity": amount(300000),
            "total_debt": amount(90000),
        }
    )
business["analysis_details"] = {
    "as_of": "2026-01-31",
    "identity": {
        "subject_linked": True,
        "representation_confirmed": True,
        "authorizations_applicable": False,
        "evidence_ids": ["synthetic"],
    },
    "funding": {
        "product_id": "demo-monthly",
        "justified_need": amount(60000),
        "announced_contribution": amount(6000),
        "verified_contribution": amount(6000),
        "purpose": note("Équipement synthétique ; prêt reçu et emploi des fonds séparés."),
        "implementation_start": "2026-02-01",
        "expected_start": "2026-02-01",
    },
    "repayment_history_applicable": True,
    "repayment_observations": [
        {
            "loan_reference": "existing",
            "as_of": "2026-01-31",
            "arrears": amount(0),
            "days_past_due": 0,
            "restructuring_count": 0,
        }
    ],
    "counterparties": [
        {
            "name": name,
            "period": p["period"],
            "role": "customer",
            "flow_kind": "receipt",
            "amount": amount(Decimal(p["receipts"]["value"]) * share),
        }
        for p in business["periods"]
        for name, share in [("CLIENT-A", Decimal("0.8")), ("CLIENT-B", Decimal("0.2"))]
    ],
    "customer_receipts_complete": True,
    "seasonality": note("Données historiques variables, saisonnalité annuelle non validée."),
    "dependencies": [note("Fournisseur synthétique principal : délais à suivre.")],
    "accounting": accounting,
    "working_capital_applicable": True,
    "working_capital": {
        "as_of": "2025-12-31",
        "period_start": "2025-12-01",
        "period_end": "2025-12-31",
        "inventory": amount(100000),
        "receivables": amount(700000),
        "payables": amount(120000),
        "average_inventory": amount(100000),
        "average_receivables": amount(600000),
        "average_payables": amount(120000),
        "credit_sales": amount(1000000),
        "credit_purchases": amount(500000),
        "cost_of_sales": amount(500000),
        "overdue_receivables": amount(200000),
        "overdue_payables": amount(0),
    },
    "equity": amount(300000),
    "off_balance_commitments": amount(0),
    "tax_arrears": amount(0),
    "social_arrears": amount(0),
    "project_receipts": [
        {
            "period": "2026-02-01",
            "amount": amount(50000),
            "included_in_receipts": True,
            "justification": note("Recette de projet hypothétique déjà incluse, jamais garantie."),
        }
    ],
    "projection_assumptions": [
        note(
            "Recouvrement des créances et coûts explicitement projetés ; bénéfice distinct de la caisse."
        )
    ],
    "collateral_applicable": True,
    "collateral": [
        {
            "description": "Équipement synthétique",
            "declared_value": amount(200000),
            "valuation_date": "2026-01-15",
            "known_charges": amount(0),
            "verification": note(
                "Contrôle de transcription synthétique, authenticité non évaluée."
            ),
            "realization_limits": [
                note("Valeur de réalisation, délai et frais de recouvrement non garantis.")
            ],
        }
    ],
}
save("business_profitable_cash_tension", business)
seasonal = deepcopy(business)
seasonal["name"] = "Activité saisonnière synthétique : encaissement faible avant récolte"
for p, value in zip(seasonal["periods"], [50000, 700000, 300000]):
    p["receipts"] = amount(value)
seasonal["analysis_details"]["counterparties"] = [
    {
        "name": name,
        "period": p["period"],
        "role": "customer",
        "flow_kind": "receipt",
        "amount": amount(Decimal(p["receipts"]["value"]) * share),
    }
    for p in seasonal["periods"]
    for name, share in [("CLIENT-A", Decimal(".8")), ("CLIENT-B", Decimal(".2"))]
]
seasonal["analysis_details"]["seasonality"] = note(
    "Récolte hypothétique en mars ; déficit de février visible malgré un cumul trimestriel positif."
)
save("business_seasonal", seasonal)

for name, core, model, engine in [
    ("individual_control", "individuals", IndividualCase, IndividualAnalysisEngine),
    ("individual_incomplete", "individuals", IndividualCase, IndividualAnalysisEngine),
    ("business_profitable_cash_tension", "businesses", BusinessCase, BusinessAnalysisEngine),
    ("business_seasonal", "businesses", BusinessCase, BusinessAnalysisEngine),
]:
    case = model.model_validate(json.loads((ROOT / (name + ".json")).read_text()))
    policy = load_policy(core + "-illustrative-v1", core, "demonstration", "synthetic")
    report = engine().analyze(case, policy, "demonstration")
    (ROOT / (name + ".report.json")).write_text(report.model_dump_json(indent=2) + "\n")
    (ROOT / (name + ".report.md")).write_text(render_french(report))
    print(
        name,
        "sections",
        len(report.sections),
        "score",
        report.scoring["criteria_score"],
        "état",
        report.operating_state,
    )
