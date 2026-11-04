from datetime import date
from decimal import Decimal

from credit.shared.contracts import Contract


class BusinessPeriodResult(Contract):
    period: date
    operating_receipts: Decimal | None
    cash_available_for_debt: Decimal | None
    existing_debt_service: Decimal | None
    new_debt_service: Decimal | None
    margin_after_debt: Decimal | None
    closing_cash: Decimal | None
    debt_service_coverage: Decimal | None
    financing_received: Decimal | None
    financed_uses: Decimal | None

    @property
    def closing_reserve_or_cash(self):
        return self.closing_cash
