"""Projection d'affichage des résultats calculés ; aucun nouveau score ni seuil."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext


def number(value):
    if value is None or isinstance(value, (bool, float)):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def money(value):
    return (
        format(value.quantize(Decimal(".01"), rounding=ROUND_HALF_UP), "f")
        if value is not None
        else None
    )


def group(title, entries, value=None, center=None):
    complete = all(amount is not None and amount >= 0 for _, _, amount in entries) and (
        not center or value is not None
    )
    total = sum((amount for _, _, amount in entries), Decimal(0)) if complete else None
    return {
        "title": title,
        "value": money(value if center else total),
        "status": "incomplete" if total is None else "zero" if total == 0 else "available",
        "total": money(total),
        "segments": [
            {
                "id": key,
                "label": label,
                "value": money(amount),
                "percentage": format((amount * 100 / total).quantize(Decimal(".0001")), "f")
                if total is not None and total > 0 and amount is not None
                else None,
            }
            for key, label, amount in entries
        ],
    }


def budget_chart(report, snapshot, *, case_id, assessment_id):
    """Lire exclusivement l'instantané analysé, jamais le dossier modifié depuis."""
    business = report["core"] == "businesses"
    reference = {p["period"]: p.get("basis", "unknown") for p in snapshot.get("periods", [])}
    periods = []
    with localcontext() as ctx:
        ctx.prec = 64
        for row in report.get("financial_calculations", {}).get("periods", []):
            existing = number(row.get("existing_debt_service"))
            new = number(row.get("new_debt_service"))
            margin = number(row.get("margin_after_debt" if business else "margin_after_credit"))
            debt = [
                ("existing", "Échéances existantes", existing),
                ("requested", "Échéance du nouveau crédit", new),
            ]
            capacity = list(debt)
            if margin is not None and margin > 0:
                capacity.append(("remaining", "Marge après remboursement", margin))
            opening_amount = (
                snapshot.get("opening_cash" if business else "mobilizable_reserve") or {}
            )
            opening = (
                number(opening_amount.get("value"))
                if opening_amount.get("state") in {"known", "estimated"}
                else None
            )
            balance = number(row.get("closing_cash" if business else "projected_reserve"))
            liquidity = []
            liquidity_explanation = "Comparaison au solde initial, avec les flux cumulés depuis le début de la projection."
            if opening is None or balance is None:
                liquidity = [
                    ("initial", "Solde initial mobilisable", opening),
                    ("change", "Variation cumulée de la projection", None),
                ]
            elif balance >= opening:
                liquidity = [
                    ("initial", "Solde initial mobilisable", opening),
                    ("increase", "Variation nette positive cumulée", balance - opening),
                ]
            elif balance >= 0:
                liquidity_explanation = (
                    "Part restante et réduction du solde initial, cumulées jusqu’à cette période."
                )
                liquidity = [
                    ("funds", "Solde projeté restant", balance),
                    ("decrease", "Réduction par rapport au solde initial", opening - balance),
                ]
            else:
                liquidity_explanation = "Solde initial entièrement absorbé et manque supplémentaire projeté à cette période."
                liquidity = [
                    ("initial", "Solde initial absorbé", opening),
                    (
                        "shortfall",
                        "Manque de trésorerie projeté"
                        if business
                        else "Déficit de réserve projeté",
                        -balance,
                    ),
                ]
            capacity_view = group(
                "Marge après dette" if business else "Marge après crédit",
                capacity,
                margin,
                center=True,
            )
            capacity_view["explanation"] = (
                "Capacité disponible après les sorties nécessaires à l’activité."
                if business
                else "Marge après charges essentielles et échéances de crédit."
            )
            capacity_view["available_before_debt"] = money(
                number(row.get("cash_available_for_debt" if business else "available_before_debt"))
            )
            capacity_view["debt_due"] = (
                money(existing + new) if existing is not None and new is not None else None
            )
            debt_view = group("Service de la dette", debt)
            debt_view["explanation"] = (
                "Capital, intérêts et frais exigibles sur la période ; pas le capital restant dû."
            )
            liquidity_view = group(
                "Trésorerie projetée" if business else "Réserve projetée",
                liquidity,
                balance,
                center=True,
            )
            liquidity_view["explanation"] = liquidity_explanation
            liquidity_view["negative"] = balance is not None and balance < 0
            periods.append(
                {
                    "period": row["period"],
                    "basis": reference.get(row["period"], "unknown"),
                    "capacity": capacity_view,
                    "debt": debt_view,
                    "liquidity": liquidity_view,
                    "deficit": margin is not None and margin < 0,
                }
            )
    return {
        "schema_version": "credit-pme.credit-overview.v2",
        "case_id": case_id,
        "case_label": snapshot.get("name"),
        "assessment_id": assessment_id,
        "core": report["core"],
        "currency": "XOF",
        "engine_version": report["engine_version"],
        "periods": periods,
        "notice": "Projection après exploitation, dette, financements reçus et emploi des fonds. "
        "Une trésorerie positive ne vaut pas accord de crédit."
        if business
        else "Marge et réserve sous les hypothèses du dossier. Aucun accord de crédit automatique.",
    }
