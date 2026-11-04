from credit.shared.calculation import Context, subtract, total
from credit.businesses.results import BusinessPeriodResult
from credit.shared.scoring import CriteriaEngine, PredictiveModel

BusinessCriteriaEngine = CriteriaEngine
BusinessPredictiveModel = PredictiveModel


def analyze(case, scenario=None):
    ctx = Context(case, scenario)
    balance = ctx.amount(case.opening_cash, "trésorerie initiale")
    rows = []
    for p in case.periods:
        receipts = ctx.revenue(ctx.amount(p.receipts, f"encaissements/{p.period}"), p.period)
        operating = ctx.expense(ctx.amount(p.operating_expenses, f"exploitation/{p.period}"))
        withdrawals = ctx.amount(p.household_withdrawals, f"ménage/{p.period}", False)
        if p.household_included_in_operating:
            withdrawals = 0
        necessary = total(
            [
                operating,
                withdrawals,
                ctx.amount(p.taxes, f"impôts/{p.period}", False),
                ctx.amount(p.essential_investments, f"investissements/{p.period}", False),
            ]
        )
        available = subtract(receipts, necessary)
        existing = ctx.debt(case.existing_loans, p.period)
        new = ctx.debt([case.requested_loan], p.period)
        debt = total([existing, new])
        margin = subtract(available, debt)
        financing = ctx.amount(p.requested_loan_disbursement, f"financement/{p.period}", False)
        uses = ctx.amount(p.financed_uses, f"emploi des fonds/{p.period}", False)
        balance = subtract(total([balance, margin, financing]), uses)
        ratio = (
            available / debt if debt is not None and debt > 0 and available is not None else None
        )
        rows.append(
            BusinessPeriodResult(
                period=p.period,
                operating_receipts=receipts,
                cash_available_for_debt=available,
                existing_debt_service=existing,
                new_debt_service=new,
                margin_after_debt=margin,
                closing_cash=balance,
                debt_service_coverage=ratio,
                financing_received=financing,
                financed_uses=uses,
            )
        )
    result = ctx.finish(
        rows,
        [
            "Flux directs : aucune seconde déduction de variation de BFR.",
            "Les emplois financés sont distincts des investissements essentiels.",
            "Aucun indicateur de rentabilité déduit des seuls flux de trésorerie.",
        ],
    )
    result.assumptions["project"] = case.project_assumptions
    return result
