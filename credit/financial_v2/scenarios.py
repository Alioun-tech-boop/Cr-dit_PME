"""Stress sur copie, conservation des retards et recherche inverse bornée."""

from copy import deepcopy
from datetime import date
from decimal import Decimal
from credit.shared.calculation import Context
from credit.shared.normalization import effective_case
from credit.shared.schedule import rounded, monthly_schedule


def amount(reader, value, path):
    if value is None:
        return None
    return reader.amount(value, path)


def set_value(raw, field, value):
    raw[field] = {"value": str(rounded(value)), "state": "estimated", "evidence_ids": []}


def prepare(case, scenario, facts):
    effective, notes = effective_case(case)
    raw = effective.model_dump(mode="json")
    reader = Context(effective, None)
    business = hasattr(case, "opening_cash")
    dates = [p.period for p in effective.periods]
    splits = {s.period: s for s in facts.cost_splits}
    costs_sensitivity = {}
    if scenario.loss_source:
        sources = (
            {
                c.name
                for c in case.analysis_details.counterparties
                if c.role == "customer" and c.flow_kind == "receipt"
            }
            if business
            else {s.source for p in case.periods for s in p.incomes}
        )
        if scenario.loss_source not in sources:
            raise ValueError("Source perdue non identifiée dans le dossier")
    for i, p in enumerate(effective.periods):
        if business:
            value = amount(reader, p.receipts, f"receipts.{i}")
            if value is None:
                raise ValueError("Encaissements critiques inconnus pour le scénario")
            set_value(raw["periods"][i], "receipts", value * (1 - scenario.revenue_drop))
            if scenario.loss_source:
                selected = [
                    c
                    for c in case.analysis_details.counterparties
                    if c.period == p.period
                    and c.name == scenario.loss_source
                    and c.role == "customer"
                    and c.flow_kind == "receipt"
                ]
                if not case.analysis_details.customer_receipts_complete:
                    raise ValueError(
                        "Client perdu : ventilation complète et encaissements identifiés nécessaires"
                    )
                loss = sum_required([amount(reader, c.amount, "client perdu") for c in selected])
                updated = value * (1 - scenario.revenue_drop) - loss * (1 - scenario.revenue_drop)
                if updated < 0:
                    raise ValueError("Client perdu supérieur aux encaissements")
                set_value(raw["periods"][i], "receipts", updated)
            operating = amount(reader, p.operating_expenses, f"operating.{i}")
            if operating is None:
                raise ValueError("Coûts professionnels critiques inconnus")
            if scenario.variable_cost_increase:
                split = splits.get(p.period)
                if not split or not split.complete:
                    raise ValueError("Ventilation fixe/variable complète nécessaire")
                fixed = amount(reader, split.fixed, "coûts fixes")
                variable = amount(reader, split.variable, "coûts variables")
                if fixed is None or variable is None or fixed + variable != operating:
                    raise ValueError(
                        "Ventilation fixe/variable à rapprocher des charges d’exploitation"
                    )
                operating = fixed + variable * (1 + scenario.variable_cost_increase)
                costs_sensitivity[p.period.isoformat()] = {
                    "fixed": fixed,
                    "variable": variable,
                    "formula": "fixes + variables × (1 + hausse explicite)",
                }
            set_value(
                raw["periods"][i], "operating_expenses", operating * (1 + scenario.expense_increase)
            )
        else:
            for j, inc in enumerate(p.incomes):
                value = amount(reader, inc.net, f"incomes.{i}.{j}")
                if value is None:
                    raise ValueError("Revenu critique inconnu pour le scénario")
                if inc.kind == "self_employed_net" and inc.activity_receipts is not None:
                    costs = amount(reader, inc.necessary_professional_costs, "coûts professionnels")
                    receipts = amount(reader, inc.activity_receipts, "recettes professionnelles")
                    if costs is None or receipts is None or receipts - costs != value:
                        raise ValueError(
                            "Rapprocher revenu personnel et coûts professionnels avant stress"
                        )
                if inc.source == scenario.loss_source:
                    value = Decimal(0)
                target = raw["periods"][i]["incomes"][j]
                set_value(target, "net", value * (1 - scenario.revenue_drop))
                # Le choc porte sur le revenu personnel soutenable, pas le CA de l'activité.
                if inc.kind == "self_employed_net":
                    target["activity_receipts"] = None
                    target["necessary_professional_costs"] = None
                    target["professional_costs_already_deducted"] = True

            if p.payroll_loan_treatment == "after_loan_deductions":
                # Baisse appliquée au net reconstitué avant prêt, retenue inchangée : pas de double déduction.
                d = amount(reader, p.payroll_loan_deductions, "retenues")
                if d is None:
                    raise ValueError("Retenues inconnues")
                first = raw["periods"][i]["incomes"][0]
                net = Decimal(first["net"]["value"]) - d * scenario.revenue_drop
                if net < 0:
                    raise ValueError(
                        "Scénario net après retenues négatif : calendrier documenté nécessaire"
                    )
                set_value(first, "net", net)
            e = amount(reader, p.essential_expenses, "charges essentielles")
            if e is None:
                raise ValueError("Charges essentielles critiques inconnues")
            set_value(raw["periods"][i], "essential_expenses", e * (1 + scenario.expense_increase))
    if scenario.delay_amount:
        if scenario.delay_from not in dates or scenario.delay_to not in dates:
            raise ValueError("Retard hors horizon : fournir les périodes futures explicites")
        a, b = dates.index(scenario.delay_from), dates.index(scenario.delay_to)
        if business:
            initial = Decimal(raw["periods"][a]["receipts"]["value"])
            if scenario.delay_amount > initial:
                raise ValueError("Retard supérieur à l’encaissement retenu")
            set_value(raw["periods"][a], "receipts", initial - scenario.delay_amount)
            set_value(
                raw["periods"][b],
                "receipts",
                Decimal(raw["periods"][b]["receipts"]["value"]) + scenario.delay_amount,
            )
        else:
            if any(p.payroll_loan_treatment != "before_loan_deductions" for p in effective.periods):
                raise ValueError(
                    "Retard : revenu avant retenues et calendrier de prélèvement documentés nécessaires"
                )
            # Déplacer une fraction proportionnelle des sources retenues, une seule fois.
            total = sum(Decimal(x["net"]["value"]) for x in raw["periods"][a]["incomes"])
            if scenario.delay_amount > total:
                raise ValueError("Retard supérieur au revenu retenu")
            remaining = scenario.delay_amount
            for j, inc in enumerate(raw["periods"][a]["incomes"]):
                old = Decimal(inc["net"]["value"])
                moved = (
                    remaining
                    if j == len(raw["periods"][a]["incomes"]) - 1
                    else rounded(old * scenario.delay_amount / total)
                )
                remaining -= moved
                set_value(inc, "net", old - moved)
            template = deepcopy(raw["periods"][a]["incomes"][0])
            template["source"] = "Encaissement retardé documenté : " + scenario.id
            template["kind"] = (
                "salary"
                if case.profile == "employee"
                else "pension"
                if case.profile == "retired"
                else "self_employed_net"
            )
            template["activity_receipts"] = None
            template["necessary_professional_costs"] = None
            template["professional_costs_already_deducted"] = case.profile == "self_employed"
            set_value(template, "net", scenario.delay_amount)
            raw["periods"][b]["incomes"].append(template)
    if business:
        for counterparty in raw["analysis_details"]["counterparties"]:
            if counterparty["role"] == "customer" and counterparty["flow_kind"] == "receipt":
                old = counterparty["amount"].get("value")
                if old is not None:
                    retained = Decimal(old) * (1 - scenario.revenue_drop)
                    set_value(
                        counterparty,
                        "amount",
                        Decimal(0) if counterparty["name"] == scenario.loss_source else retained,
                    )
        if scenario.delay_amount or scenario.project_delay_periods:
            raw["analysis_details"]["customer_receipts_complete"] = False
            notes.append(
                "Ventilation client non prolongée lors du déplacement agrégé : concentration après retard à rapprocher."
            )
    if scenario.project_delay_periods:
        if not business or not case.analysis_details.project_receipts:
            raise ValueError("Recettes de projet identifiées nécessaires au retard de démarrage")
        deltas = {i: Decimal(0) for i in range(len(dates))}
        for receipt in case.analysis_details.project_receipts:
            if not receipt.included_in_receipts:
                continue
            index = dates.index(receipt.period)
            target = index + scenario.project_delay_periods
            if target >= len(dates):
                raise ValueError("Retard de projet hors horizon : projections futures nécessaires")
            value = amount(reader, receipt.amount, "recette de projet")
            if value is None:
                raise ValueError("Recette de projet inconnue")
            retained = value * (1 - scenario.revenue_drop)
            deltas[index] -= retained
            deltas[target] += retained
        for i, delta in deltas.items():
            new = Decimal(raw["periods"][i]["receipts"]["value"]) + delta
            if new < 0:
                raise ValueError("Recette de projet supérieure au flux retenu")
            set_value(raw["periods"][i], "receipts", new)
        # Les références de recettes suivent aussi le déplacement pour les sous-analyses.
        for receipt in raw["analysis_details"]["project_receipts"]:
            if receipt["included_in_receipts"]:
                receipt["period"] = dates[
                    dates.index(date.fromisoformat(receipt["period"]))
                    + scenario.project_delay_periods
                ].isoformat()
    if scenario.rate_increase:
        loan = case.requested_loan
        if scenario.rate_contract_reference not in {
            e.id for e in case.evidence if e.status == "verified"
        }:
            raise ValueError("Clause de taux variable à justifier par une preuve contrôlée")
        if loan.amortization_method != "monthly_constant" or loan.annual_nominal_rate is None:
            raise ValueError(
                "Choc de taux : contrat mensuel amortissable et taux connus nécessaires"
            )
        fees = [amount(reader, p.fees, "frais") for p in loan.schedule]
        if None in fees or len(set(fees)) != 1:
            raise ValueError("Frais contractuels constants nécessaires")
        updated = monthly_schedule(
            loan.principal.value,
            loan.annual_nominal_rate + scenario.rate_increase,
            len(loan.schedule),
            loan.schedule[0].period,
            fees[0],
        )
        updated.reference = loan.reference
        raw["requested_loan"] = updated.model_dump(mode="json")
    for row in raw["periods"]:
        row["basis"] = "forecast"
    notes.append(
        "Flux hypothétiques de simulation ; observations historiques originales conservées séparément."
    )
    return type(case).model_validate(raw), notes + [scenario.rationale], costs_sensitivity


def sum_required(values):
    if None in values:
        raise ValueError("Valeur nécessaire inconnue")
    return sum(values, Decimal(0))


def search(evaluate, lower, upper, steps=20, tolerance=Decimal(".000001"), integer=False):
    """Sonde tout l'intervalle avant dichotomie ; pas de monotonie supposée en silence."""
    points = [lower + (upper - lower) * i / steps for i in range(steps + 1)]
    if integer:
        points = sorted(set(Decimal(int(x)) for x in points) | {lower, upper})
    values = [evaluate(x) for x in points]
    if any(v is None for v in values):
        return {
            "status": "incomplete",
            "threshold": None,
            "reason": "Indicateur non calculable dans l’intervalle",
            "evaluations": len(points),
        }
    monotone = all(a >= b for a, b in zip(values, values[1:]))
    brackets = [
        (a, b) for a, b, x, y in zip(points, points[1:], values, values[1:]) if x > 0 and y <= 0
    ]
    if values[0] <= 0:
        return {
            "status": "already_breached",
            "threshold": lower,
            "margin": values[0],
            "method": "bounded_grid",
            "evaluations": len(points),
        }
    if not brackets:
        return {
            "status": "not_found_in_tested_interval",
            "threshold": None,
            "method": "bounded_grid",
            "interval": [lower, upper],
            "monotonicity_verified_on_grid": monotone,
            "evaluations": len(points),
        }
    lo, hi = brackets[0]
    if not monotone or integer:
        if integer:
            exact = [(x, evaluate(Decimal(x))) for x in range(int(lo), int(hi) + 1)]
            hi = next((Decimal(x) for x, y in exact if y is not None and y <= 0), hi)
        return {
            "status": "found_bracket",
            "threshold": hi,
            "bracket": [lo, hi],
            "method": "bounded_grid",
            "monotonicity_verified_on_grid": monotone,
            "evaluations": len(points),
        }
    for _ in range(64):
        if hi - lo <= tolerance:
            break
        mid = (lo + hi) / 2
        value = evaluate(mid)
        if value is None:
            return {"status": "incomplete", "threshold": None}
        if value <= 0:
            hi = mid
        else:
            lo = mid
    return {
        "status": "found",
        "threshold": hi,
        "bracket": [lo, hi],
        "method": "bisection_after_bounded_monotonicity_check",
        "monotonicity_verified_on_grid": True,
        "resolution": tolerance,
        "evaluations": len(points),
    }
