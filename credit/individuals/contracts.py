from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from credit.shared.contracts import Amount, BaseCase, Contract
from credit.printing.profile import RecordDetails
from credit.assessment.inputs import IndividualDetails


class Income(Contract):
    source: str
    kind: Literal["salary", "pension", "self_employed_net"]
    net: Amount
    professional_costs_already_deducted: bool = False
    activity_receipts: Amount | None = None
    necessary_professional_costs: Amount | None = None

    @model_validator(mode="after")
    def net_components(self):
        if (self.activity_receipts is None) != (self.necessary_professional_costs is None):
            raise ValueError("Encaissements et coûts professionnels doivent être fournis ensemble")
        if self.activity_receipts is not None and self.kind != "self_employed_net":
            raise ValueError("Composantes professionnelles réservées aux indépendants")
        return self


class IndividualPeriod(Contract):
    period: date
    basis: Literal["observed", "forecast"] = "forecast"
    incomes: list[Income] = Field(min_length=1)
    essential_expenses: Amount
    payroll_loan_treatment: Literal["before_loan_deductions", "after_loan_deductions", "unclear"]
    payroll_loan_deductions: Amount


class IncomeHistory(Contract):
    period: date
    net_personal_income: Amount


class IndividualCase(BaseCase):
    record_details: RecordDetails = Field(default_factory=RecordDetails)
    analysis_details: IndividualDetails = Field(default_factory=IndividualDetails)
    profile: Literal["employee", "retired", "self_employed"]
    household_scope: str
    mobilizable_reserve: Amount
    periods: list[IndividualPeriod]
    income_history: list[IncomeHistory] = Field(default_factory=list)

    @model_validator(mode="after")
    def periods_valid(self):
        dates = [p.period for p in self.periods]
        if not dates or dates != sorted(set(dates)):
            raise ValueError("Périodes obligatoires, uniques et croissantes")
        for loan in self.existing_loans + [self.requested_loan]:
            if any(p.period not in dates for p in loan.schedule):
                raise ValueError("Échéance hors horizon")
        history_dates = [p.period for p in self.income_history]
        if history_dates != sorted(set(history_dates)) or any(d >= dates[0] for d in history_dates):
            raise ValueError("Historique unique, croissant et antérieur aux projections")
        return self
