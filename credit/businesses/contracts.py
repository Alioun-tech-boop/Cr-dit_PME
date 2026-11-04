from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from credit.shared.contracts import Amount, BaseCase, Contract


class BusinessPeriod(Contract):
    period: date
    receipts: Amount
    operating_expenses: Amount
    taxes: Amount
    essential_investments: Amount
    household_withdrawals: Amount
    household_included_in_operating: bool = False
    requested_loan_disbursement: Amount
    financed_uses: Amount


class BusinessCase(BaseCase):
    mode: Literal["structured_accounts", "reconstructed_cashflows"]
    activity: str
    opening_cash: Amount
    periods: list[BusinessPeriod]
    historical_cashflows: list[BusinessPeriod] = Field(default_factory=list)
    project_assumptions: list[str]
    receivables: Amount | None = None
    payables: Amount | None = None
    inventory: Amount | None = None

    @model_validator(mode="after")
    def periods_valid(self):
        dates = [p.period for p in self.periods]
        if not dates or dates != sorted(set(dates)):
            raise ValueError("Périodes obligatoires, uniques et croissantes")
        for loan in self.existing_loans + [self.requested_loan]:
            if any(p.period not in dates for p in loan.schedule):
                raise ValueError("Échéance hors horizon")
        disbursements = [p.requested_loan_disbursement.value for p in self.periods]
        if (
            all(v is not None for v in disbursements)
            and self.requested_loan.principal.value is not None
        ):
            if sum(disbursements) != self.requested_loan.principal.value:
                raise ValueError("Décaissements du crédit différents du capital demandé")
        history_dates = [p.period for p in self.historical_cashflows]
        if history_dates != sorted(set(history_dates)) or any(d >= dates[0] for d in history_dates):
            raise ValueError("Historique unique, croissant et antérieur aux projections")
        return self
