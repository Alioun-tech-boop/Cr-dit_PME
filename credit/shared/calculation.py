from decimal import Decimal

from credit.shared.contracts import Amount, Scenario
from credit.shared.results import AnalysisResult, FinancialFindings
from credit.shared.schedule import rounded

ZERO = Decimal(0)


def total(values):
    values = list(values)
    return None if any(v is None for v in values) else sum(values, ZERO)


def subtract(a, b):
    return None if a is None or b is None else a - b


class Context:
    def __init__(self, case, scenario):
        self.case = case
        self.scenario = scenario or Scenario(name="Base sans stress")
        self.missing = list(case.missing_information)
        self.unproven = []
        self.delay_valid = False
        for loan in case.existing_loans + [case.requested_loan]:
            self.amount(loan.principal, f"capital/{loan.reference}")

    def amount(self, amount: Amount, label, critical=True):
        if not amount.evidence_ids:
            self.unproven.append(label)
        if amount.state == "unknown":
            self.missing.append(label)
            return None
        if amount.state == "not_applicable":
            if critical:
                self.missing.append(label + " : non applicable à clarifier")
                return None
            return ZERO
        if any(
            e.status in ("missing", "contradictory", "unverified_extracted")
            for e in self.case.evidence
            if e.id in amount.evidence_ids
        ):
            self.missing.append(
                label + " : preuve manquante, contradictoire ou transcription non revue"
            )
            return None
        return amount.value

    def debt(self, loans, period):
        if any(not loan.schedule and loan.principal.value is None for loan in loans):
            self.missing.append(f"Échéancier inconnu/{period}")
            return None
        return total(
            self.amount(getattr(p, k), f"dette {loan.reference}/{period}/{k}", k == "principal")
            for loan in loans
            for p in loan.schedule
            if p.period == period
            for k in ("principal", "interest", "fees")
        )

    def revenue(self, value, period):
        if value is None:
            return None
        s = self.scenario
        value = rounded(value * (1 - s.revenue_drop))
        if s.delay_from == period:
            self.delay_valid = True
            if s.delay_amount > value:
                raise ValueError("Encaissement retardé supérieur au montant disponible sous stress")
            value -= s.delay_amount
        if s.delay_to == period:
            if s.delay_amount and not self.delay_valid:
                self.missing.append("Encaissement source inconnu : report non calculable")
                return None
            value += s.delay_amount
        return value

    def expense(self, value):
        return None if value is None else rounded(value * (1 + self.scenario.expense_increase))

    def finish(self, rows, observations, variability=None):
        dates = [p.period for p in self.case.periods]
        if self.scenario.delay_amount and (
            self.scenario.delay_from not in dates or self.scenario.delay_to not in dates
        ):
            raise ValueError("Retard hors horizon")
        balances = [(r.closing_reserve_or_cash, r.period) for r in rows]
        minimum = min(balances) if all(v is not None for v, _ in balances) else (None, None)
        return AnalysisResult(
            analysis_type="individual" if hasattr(self.case, "household_scope") else "business",
            status="incomplete" if self.missing else "complete",
            periods=rows,
            information_requested=sorted(set(self.missing)),
            documentary_quality={
                "evidence_statuses": {e.id: e.status for e in self.case.evidence},
                "amounts_without_evidence": sorted(set(self.unproven)),
                "note": "Qualité documentaire distincte de la situation financière ; aucun taux de confiance.",
            },
            financial_findings=FinancialFindings(
                deficit_periods=[
                    r.period
                    for r in rows
                    if r.margin_after_debt is not None and r.margin_after_debt < 0
                ],
                negative_balance_periods=[
                    r.period
                    for r in rows
                    if r.closing_reserve_or_cash is not None and r.closing_reserve_or_cash < 0
                ],
                minimum_balance=minimum[0],
                minimum_balance_date=minimum[1],
                income_variability_cv=variability,
                observations=observations,
            ),
            assumptions={
                "scenario": self.scenario.model_dump(mode="json"),
                "currency": self.case.currency,
                "rounding": "0.01 HALF_UP",
                "horizon": "Périodes explicites ; aucune extrapolation automatique",
            },
        )
