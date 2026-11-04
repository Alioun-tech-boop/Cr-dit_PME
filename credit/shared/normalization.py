from credit.shared.calculation import Context, total
from credit.shared.arithmetic import deterministic


@deterministic
def effective_case(case):
    """Les charges essentielles futures hors total sont ajoutées une seule fois, sur copie."""
    if not hasattr(case.analysis_details, "expenses"):
        return case, []
    raw = case.model_dump(mode="json")
    reader = Context(case, None)
    notes = []
    dates = {p.period: i for i, p in enumerate(case.periods)}
    for expense in case.analysis_details.expenses:
        if expense.period not in dates:
            raise ValueError("Dépense essentielle hors horizon : fournir explicitement la période")
    for period, i in dates.items():
        extras = [
            e
            for e in case.analysis_details.expenses
            if e.period == period and not e.included_in_total
        ]
        if not extras:
            continue
        amounts = [case.periods[i].essential_expenses] + [e.amount for e in extras]
        value = total(reader.amount(a, f"charges/{period}") for a in amounts)
        raw["periods"][i]["essential_expenses"] = {
            "value": str(value) if value is not None else None,
            "state": "unknown"
            if value is None
            else "estimated"
            if any(a.state == "estimated" for a in amounts)
            else "known",
            "evidence_ids": sorted({e for a in amounts for e in a.evidence_ids}),
        }
        for expense in raw["analysis_details"]["expenses"]:
            if expense["period"] == period.isoformat() and not expense["included_in_total"]:
                expense["included_in_total"] = True
        notes.append(
            f"{period} : charges essentielles supplémentaires hors total intégrées sans double comptage."
        )
    return type(case).model_validate(raw), notes
