from datetime import date
from decimal import Decimal

from credit.shared.contracts import Contract


class IndividualPeriodResult(Contract):
    period: date
    net_retained_income: Decimal | None
    available_before_debt: Decimal | None
    existing_debt_service: Decimal | None
    new_debt_service: Decimal | None
    margin_after_credit: Decimal | None
    projected_reserve: Decimal | None
    debt_to_income: Decimal | None

    @property
    def margin_after_debt(self):
        return self.margin_after_credit

    @property
    def closing_reserve_or_cash(self):
        return self.projected_reserve
