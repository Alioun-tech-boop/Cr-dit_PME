from credit.shared.arithmetic import deterministic
from credit.shared.normalization import effective_case
from decimal import Decimal

from credit.shared.calculation import Context, subtract, total
from credit.individuals.results import IndividualPeriodResult
from credit.shared.scoring import CriteriaEngine, PredictiveModel

# Interfaces propres au noyau, sans implémentation de score inventée.
IndividualCriteriaEngine = CriteriaEngine
IndividualPredictiveModel = PredictiveModel


@deterministic
def analyze(case, scenario=None):
    case, _ = effective_case(case)
    ctx = Context(case, scenario)
    balance = ctx.amount(case.mobilizable_reserve, "réserve mobilisable")
    rows = []
    historical = [
        ctx.amount(p.net_personal_income, f"historique/{p.period}") for p in case.income_history
    ]
    for period in case.periods:
        incomes = []
        for income in period.incomes:
            value = ctx.amount(income.net, f"revenu {income.source}/{period.period}")
            if income.kind == "self_employed_net" and income.activity_receipts is not None:
                receipts = ctx.amount(
                    income.activity_receipts, f"activité encaissements/{income.source}"
                )
                costs = ctx.amount(
                    income.necessary_professional_costs, f"activité coûts/{income.source}"
                )
                computed = subtract(receipts, costs)
                if computed is None or value is None or computed != value:
                    ctx.missing.append(
                        f"Rapprocher revenu net et coûts professionnels : {income.source}"
                    )
                    value = None
            elif (
                income.kind == "self_employed_net"
                and not income.professional_costs_already_deducted
            ):
                ctx.missing.append(
                    f"Justifier revenu net après coûts professionnels : {income.source}"
                )
                value = None
            incomes.append(value)
        income = total(incomes)
        deduction = ctx.amount(
            period.payroll_loan_deductions, f"retenues prêts/{period.period}", False
        )
        if period.payroll_loan_treatment == "unclear":
            ctx.missing.append(f"Clarifier retenues salariales/{period.period}")
            income = None
        elif period.payroll_loan_treatment == "after_loan_deductions":
            income = total([income, deduction])
        income = ctx.revenue(income, period.period)
        expenses = ctx.expense(
            ctx.amount(period.essential_expenses, f"dépenses essentielles/{period.period}")
        )
        available = subtract(income, expenses)
        existing = ctx.debt(case.existing_loans, period.period)
        new = ctx.debt([case.requested_loan], period.period)
        if (
            period.payroll_loan_treatment == "after_loan_deductions"
            and deduction is not None
            and existing is not None
            and deduction > existing
        ):
            ctx.missing.append(f"Rapprocher retenues et dettes existantes/{period.period}")
            available = None
        debt = total([existing, new])
        margin = subtract(available, debt)
        balance = total([balance, margin])
        ratio = debt / income if income is not None and income > 0 and debt is not None else None
        rows.append(
            IndividualPeriodResult(
                period=period.period,
                net_retained_income=income,
                available_before_debt=available,
                existing_debt_service=existing,
                new_debt_service=new,
                margin_after_credit=margin,
                projected_reserve=balance,
                debt_to_income=ratio,
            )
        )
    variability = None
    if len(historical) >= 3 and all(v is not None for v in historical):
        mean = total(historical) / len(historical)
        if mean > 0:
            variability = (
                sum((v - mean) ** 2 for v in historical) / Decimal(len(historical))
            ).sqrt() / mean
    return ctx.finish(
        rows,
        [
            "Revenus personnels nets ; capital du nouveau crédit exclu du revenu.",
            "Retenues de prêts réintégrées si salaire déjà net de ces retenues.",
        ],
        variability,
    )
