import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from credit.shared.arithmetic import deterministic
from credit.shared.contracts import Amount, Loan, Payment

CENT = Decimal("0.01")


@deterministic
def rounded(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@deterministic
def monthly_schedule(
    principal: Decimal,
    annual_rate: Decimal,
    months: int,
    first_payment: date,
    fee_per_payment: Decimal = Decimal(0),
) -> Loan:
    if (
        not all(v.is_finite() for v in [principal, annual_rate, fee_per_payment])
        or annual_rate > 10
        or principal >= Decimal("1e22")
        or fee_per_payment >= Decimal("1e22")
    ):
        raise ValueError("Conditions hors limites techniques")
    if principal <= 0 or annual_rate < 0 or not 1 <= months <= 600 or fee_per_payment < 0:
        raise ValueError("Conditions de prêt invalides")
    if principal != rounded(principal) or fee_per_payment != rounded(fee_per_payment):
        raise ValueError("Au plus deux décimales")
    rate = annual_rate / 12  # taux nominal exprimé en fraction : 0.12 = 12 %
    payment = rounded(
        principal / months if rate == 0 else principal * rate / (1 - (1 + rate) ** -months)
    )
    balance = principal
    schedule = []
    for i in range(months):
        month_index = first_payment.year * 12 + first_payment.month - 1 + i
        year, month = divmod(month_index, 12)
        month += 1
        day = min(first_payment.day, calendar.monthrange(year, month)[1])
        interest = rounded(balance * rate)
        capital = balance if i == months - 1 else min(balance, payment - interest)
        if capital < 0:
            raise ValueError("Échéance arrondie insuffisante")
        schedule.append(
            Payment(
                period=date(year, month, day),
                due_date=date(year, month, day),
                principal=Amount(value=capital),
                interest=Amount(value=interest),
                fees=Amount(value=fee_per_payment),
            )
        )
        balance -= capital
    return Loan(
        reference="generated",
        principal=Amount(value=principal),
        schedule=schedule,
        annual_nominal_rate=annual_rate,
    )
