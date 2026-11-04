"""Régénère uniquement les quatre jeux synthétiques livrés."""

import json
from pathlib import Path

ROOT = Path(__file__).parent


def amount(value):
    return {"value": str(value), "state": "known", "evidence_ids": ["synthetic"]}


def loan(reference, principal, payments):
    return {
        "reference": reference,
        "principal": amount(principal),
        "schedule": [
            {
                "period": date,
                "principal": amount(capital),
                "interest": amount(interest),
                "fees": amount(0),
            }
            for date, capital, interest in payments
        ],
    }


def base(name):
    return {
        "name": name,
        "currency": "XOF",
        "evidence": [
            {
                "id": "synthetic",
                "source": "Document entièrement synthétique de démonstration",
                "period": "2026-01-01",
                "currency": "XOF",
                "collected_at": "2026-01-01",
                "status": "declared",
            }
        ],
        "existing_loans": [
            loan("existing", 30000, [("2026-02-01", 10000, 1000), ("2026-03-01", 20000, 1000)])
        ],
        "requested_loan": loan(
            "requested", 60000, [("2026-02-01", 20000, 2000), ("2026-04-01", 40000, 2000)]
        ),
    }


for profile, filename, revenue, expenses in [
    ("employee", "salarie", 250000, 150000),
    ("self_employed", "independant", 180000, 120000),
]:
    case = base("Ménage fictif " + filename)
    case.update(
        profile=profile,
        household_scope="Deux adultes et deux enfants fictifs",
        mobilizable_reserve=amount(100000),
        periods=[],
    )
    for month in range(2, 5):
        case["periods"].append(
            {
                "period": f"2026-{month:02}-01",
                "incomes": [
                    {
                        "source": "Source personnelle synthétique",
                        "kind": "salary" if profile == "employee" else "self_employed_net",
                        "net": amount(revenue),
                        "professional_costs_already_deducted": profile == "self_employed",
                    }
                ],
                "essential_expenses": amount(expenses),
                "payroll_loan_treatment": "before_loan_deductions",
                "payroll_loan_deductions": amount(0),
            }
        )
    (ROOT / f"{filename}.json").write_text(json.dumps(case, indent=2, ensure_ascii=False) + "\n")

for mode, filename, receipts in [
    ("structured_accounts", "pme_structuree", 500000),
    ("reconstructed_cashflows", "petite_activite", 300000),
]:
    case = base("Entreprise fictive " + filename)
    case.update(
        mode=mode,
        activity="Commerce fictif",
        opening_cash=amount(100000),
        project_assumptions=[
            "Le crédit finance un équipement synthétique de 60000 XOF.",
            "Aucune croissance additionnelle présumée.",
        ],
        periods=[],
    )
    for month in range(2, 5):
        case["periods"].append(
            {
                "period": f"2026-{month:02}-01",
                "receipts": amount(receipts),
                "operating_expenses": amount(200000),
                "taxes": amount(10000),
                "essential_investments": amount(0),
                "household_withdrawals": amount(20000),
                "requested_loan_disbursement": amount(60000 if month == 2 else 0),
                "financed_uses": amount(60000 if month == 2 else 0),
            }
        )
    (ROOT / f"{filename}.json").write_text(json.dumps(case, indent=2, ensure_ascii=False) + "\n")

# Pour l'indépendant, rapprochement explicite du revenu personnel avec l'activité.
path = ROOT / "independant.json"
case = json.loads(path.read_text())
for period in case["periods"]:
    period["incomes"][0].update(
        activity_receipts=amount(400000), necessary_professional_costs=amount(220000)
    )
path.write_text(json.dumps(case, indent=2, ensure_ascii=False) + "\n")
