"""Compatibilité des dates : calcul seulement après rapprochement des flux mensuels."""

from collections import defaultdict
from credit.shared.calculation import total


def analyze_timing(ctx):
    unavailable = {
        "status": "not_available",
        "timeline": [],
        "minimum_balance": None,
        "information_requested": [
            "Dates complètes des flux et des échéances, rapprochées des totaux de période"
        ],
    }
    if not ctx.details.timing_complete:
        return unavailable
    business = hasattr(ctx.case, "opening_cash")
    section = ctx.sections["treasury" if business else "reserve"]
    starting = ctx.reader.amount(
        ctx.case.opening_cash if business else ctx.case.mobilizable_reserve, "solde initial daté"
    )
    if starting is None:
        return unavailable
    categories = (
        ["receipts", "necessary_outflow", "financing", "financed_use"]
        if business
        else ["income", "essential"]
    )
    totals = defaultdict(list)
    entries = []
    for flow in ctx.details.dated_flows:
        if flow.kind not in categories:
            raise ValueError("Type de flux daté incompatible avec le noyau")
        if flow.period not in {p.period for p in ctx.case.periods}:
            raise ValueError("Flux daté hors horizon")
        value = ctx.reader.amount(flow.amount, "flux daté")
        if value is None:
            return unavailable
        totals[(flow.period, flow.kind)].append(value)
        sign = -1 if flow.kind in {"essential", "necessary_outflow", "financed_use"} else 1
        entries.append((flow.date, sign * value, flow.kind))
    for row in ctx.financial.periods:
        if business:
            expected = {
                "receipts": row.operating_receipts,
                "necessary_outflow": None
                if row.operating_receipts is None or row.cash_available_for_debt is None
                else row.operating_receipts - row.cash_available_for_debt,
                "financing": row.financing_received,
                "financed_use": row.financed_uses,
            }
        else:
            expected = {
                "income": row.net_retained_income,
                "essential": None
                if row.net_retained_income is None or row.available_before_debt is None
                else row.net_retained_income - row.available_before_debt,
            }
        for kind, amount in expected.items():
            if total(totals[(row.period, kind)]) != amount:
                unavailable["information_requested"].append(
                    f"Rapprocher {kind} daté et total de {row.period}"
                )
                return unavailable
    for loan in ctx.case.existing_loans + [ctx.case.requested_loan]:
        for payment in loan.schedule:
            if payment.due_date is None:
                return unavailable
            if payment.due_date.strftime("%Y-%m") != payment.period.strftime("%Y-%m"):
                raise ValueError("Date d’échéance hors de sa période mensuelle")
            value = total(
                ctx.reader.amount(getattr(payment, k), "dette datée", k == "principal")
                for k in ["principal", "interest", "fees"]
            )
            if value is None:
                return unavailable
            entries.append((payment.due_date, -value, "debt:" + loan.reference))
    by_date = defaultdict(list)
    for day, value, kind in entries:
        by_date[day].append((value, kind))
    balance = starting
    timeline = []
    for day, flows in sorted(by_date.items()):
        balance += sum(v for v, _ in flows)
        timeline.append(
            {
                "date": day.isoformat(),
                "net_flow": sum(v for v, _ in flows),
                "closing_balance": balance,
                "kinds": sorted(k for _, k in flows),
            }
        )
    minimum = min([starting] + [p["closing_balance"] for p in timeline])
    ctx.metric(
        section,
        "intraperiod_minimum",
        minimum,
        "XOF",
        "Solde initial + flux datés rapprochés, nets par jour ; ordre intrajournalier inconnu",
    )
    if minimum < 0:
        section.alerts.append(
            "Déficit daté avant les encaissements, même si la fin du mois est positive."
        )
        section.status = "defavorable"
    return {
        "status": "available",
        "timeline": timeline,
        "minimum_balance": minimum,
        "information_requested": [],
        "limitation": "Les mouvements d’un même jour sont compensés ; leur ordre intrajournalier n’est pas connu.",
    }
