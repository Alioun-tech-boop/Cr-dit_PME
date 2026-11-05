"""Statistiques descriptives, couverture et rapprochements sur données fournies."""

from decimal import Decimal
from credit.assessment.context import ratio
from credit.assessment.contracts import DataUse
from credit.shared.contracts import Amount, SignedAmount
from credit.shared.calculation import Context


def monthly_gaps(dates):
    found = []
    for a, b in zip(dates, dates[1:]):
        if (b.year * 12 + b.month) - (a.year * 12 + a.month) > 1:
            found.append(
                {
                    "after": a.isoformat(),
                    "before": b.isoformat(),
                    "missing_months": (b.year * 12 + b.month) - (a.year * 12 + a.month) - 1,
                }
            )
    return found


def statistics(case, minimum=3, seasonality_months=24):
    business = hasattr(case, "historical_cashflows")
    reader = Context(case, None)
    rows = case.historical_cashflows if business else case.income_history
    field = "receipts" if business else "net_personal_income"
    data = [reader.amount(getattr(p, field), "historical." + p.period.isoformat()) for p in rows]
    known = [v for v in data if v is not None]
    gaps = monthly_gaps([p.period for p in rows])
    result = {
        "scope": "provided_observed_history_only",
        "provided_periods": len(data),
        "known_periods": len(known),
        "missing_period_ranges": gaps,
        "minimum_required": minimum,
        "mean": None,
        "median": None,
        "minimum": None,
        "maximum": None,
        "coefficient_of_variation": None,
        "zero_income_periods": sum(v == 0 for v in known),
        "comparable_change": None,
        "seasonality_status": "insufficient_data",
        "seasonality_profile": None,
        "formulas": {
            "mean": "Σ valeurs / nombre de périodes comparables",
            "median": "Valeur centrale, moyenne des deux centrales si effectif pair",
            "coefficient_of_variation": "Écart type de population / moyenne strictement positive",
        },
        "input_paths": [
            "historical_cashflows.*.receipts"
            if business
            else "income_history.*.net_personal_income"
        ],
        "notice": "Des statistiques historiques ne garantissent aucun revenu futur.",
    }
    if len(known) < minimum or len(known) != len(data) or gaps:
        result["status"] = "incomplete"
        return result
    ordered = sorted(known)
    n = len(ordered)
    mean = sum(known) / n
    result.update(
        status="available",
        mean=mean,
        median=ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2,
        minimum=min(known),
        maximum=max(known),
        coefficient_of_variation=((sum((v - mean) ** 2 for v in known) / n).sqrt() / mean)
        if mean > 0
        else None,
        comparable_change=ratio(known[-1] - known[0], known[0]),
    )
    if n >= seasonality_months and len({p.period.year for p in rows}) >= 2:
        months = {i: [] for i in range(1, 13)}
        for p, v in zip(rows, known):
            months[p.period.month].append(v)
        if all(len(v) >= 2 for v in months.values()):
            result.update(
                seasonality_status="descriptive_profile_not_prediction",
                seasonality_profile={str(m): sum(v) / len(v) for m, v in months.items()},
            )
    return result


def reconcile(case, facts):
    reader = Context(case, None)
    checks = []
    warnings = []
    coverage = {
        "important_amounts": 0,
        "usable_amounts": 0,
        "controlled_amounts": 0,
        "unknown_amounts": 0,
    }
    evidence = {e.id: e for e in case.evidence}

    def visit(value, path):
        if isinstance(value, (Amount, SignedAmount)):
            if not set(value.evidence_ids) <= evidence.keys():
                raise ValueError("Référence de preuve inconnue : " + path)
            coverage["important_amounts"] += 1
            known = reader.amount(value, path)
            coverage["usable_amounts" if known is not None else "unknown_amounts"] += 1
            if (
                known is not None
                and value.evidence_ids
                and all(evidence[k].status == "verified" for k in value.evidence_ids)
            ):
                coverage["controlled_amounts"] += 1
        elif hasattr(type(value), "model_fields"):
            refs = getattr(value, "evidence_ids", [])
            if not set(refs) <= evidence.keys():
                raise ValueError("Référence de preuve inconnue : " + path)
            for k in type(value).model_fields:
                visit(getattr(value, k), path + "." + k)
        elif isinstance(value, list):
            for i, v in enumerate(value):
                visit(v, f"{path}.{i}")

    visit(case, "case")
    visit(facts, "facts")
    for i, account in enumerate(facts.accounts):
        values = [
            reader.amount(getattr(account, k), f"account.{i}.{k}")
            for k in ("opening", "inflows", "outflows", "closing")
        ]
        for j, value in enumerate(values):
            if value is not None and abs(value * Decimal(account.unit_multiplier)) >= Decimal(
                "1e22"
            ):
                values[j] = None
                reader.missing.append(
                    f"account.{i}.{j} : montant hors limites après conversion d’unité"
                )
        expected = (
            None
            if None in values
            else (values[0] + values[1] - values[2]) * Decimal(account.unit_multiplier)
        )
        if expected is not None and abs(expected) >= Decimal("1e22"):
            expected = None
            reader.missing.append(f"account.{i} : solde reconstitué hors limites")
        actual = None if values[3] is None else values[3] * Decimal(account.unit_multiplier)
        difference = None if expected is None or actual is None else actual - expected
        checks.append(
            {
                "id": account.id,
                "formula": "solde final = solde initial + entrées − sorties",
                "expected_XOF": expected,
                "declared_XOF": actual,
                "difference_XOF": difference,
                "status": "incomplete"
                if difference is None
                else "matched"
                if difference == 0
                else "needs_verification",
                "scope": account.scope,
                "source_ids": account.evidence_ids,
                "period": [account.start.isoformat(), account.end.isoformat()],
            }
        )
        if difference is None or difference != 0:
            warnings.append(
                "Rapprochement du seul compte "
                + account.id
                + " à compléter ; aucune fraude déduite."
            )
    for i, a in enumerate(facts.accounts):
        for b in facts.accounts[i + 1 :]:
            if a.id == b.id and max(a.start, b.start) <= min(a.end, b.end):
                warnings.append("Périodes de compte chevauchantes : " + a.id)
    for i, p in enumerate(case.periods):
        if hasattr(p, "incomes"):
            keys = [(s.source, s.kind, tuple(sorted(s.net.evidence_ids))) for s in p.incomes]
            if len(keys) != len(set(keys)):
                warnings.append(
                    f"{p.period} : source de revenu potentiellement comptée plusieurs fois ; ventilation nécessaire."
                )
    gaps = monthly_gaps([p.period for p in case.periods])
    if gaps:
        warnings.append(
            "Projection mensuelle non continue : périodes manquantes à fournir explicitement."
        )
    if not case.analysis_details.timing_complete:
        warnings.append(
            "Données mensuelles seulement : des tensions à l’intérieur du mois peuvent ne pas être visibles."
        )
    return {
        "checks": checks,
        "warnings": warnings,
        "monthly_gaps": gaps,
        "coverage": {
            **coverage,
            "definition": "Comptage des montants fournis et admis par les validations existantes, pas une confiance prédictive.",
        },
        "scope_notice": "Aucun compte fourni n’est extrapolé à l’ensemble du patrimoine ou des dettes.",
        "information_requested": reader.missing,
    }


def add_history_section(ctx, stats):
    s = ctx.section("historical_trends", "Historique, régularité et tendances")
    ctx.use(
        s, "historical_cashflows" if hasattr(ctx.case, "historical_cashflows") else "income_history"
    )
    for key, unit in [
        ("mean", "XOF"),
        ("median", "XOF"),
        ("minimum", "XOF"),
        ("maximum", "XOF"),
        ("coefficient_of_variation", "ratio"),
        ("zero_income_periods", "périodes"),
        ("comparable_change", "ratio"),
    ]:
        ctx.metric(
            s,
            "historical_" + key,
            stats[key],
            unit,
            stats["formulas"].get(
                key, "Statistique descriptive des seules observations comparables fournies"
            ),
            paths=stats["input_paths"],
        )
    if stats["status"] != "available":
        s.missing_information.append(
            "Historique comparable complet : au moins "
            + str(stats["minimum_required"])
            + " périodes, sans mois manquant."
        )
    explanation = stats["notice"]
    if stats["seasonality_profile"] is None:
        explanation += " Saisonnalité descriptive indisponible : deux cycles annuels complets sont nécessaires ; aucune saisonnalité extrapolée."
    return ctx.finish(s, explanation)


def additional_business(ctx, facts):
    s = ctx.section("structure", "Structure financière et liquidité")
    wc = ctx.details.working_capital
    for i, b in enumerate(facts.balance_sheets):
        values = {
            k: ctx.money(
                s,
                f"facts.balance_sheets.{i}.{k}",
                getattr(b, k),
                multiplier=Decimal(b.unit_multiplier),
            )
            for k in ["stable_resources", "fixed_assets", "current_assets", "current_liabilities"]
        }
        fr = (
            None
            if values["stable_resources"] is None or values["fixed_assets"] is None
            else values["stable_resources"] - values["fixed_assets"]
        )
        bfr = None
        if wc and wc.as_of == b.as_of:
            parts = [
                ctx.money(s, "working_capital." + k, getattr(wc, k))
                for k in ("inventory", "receivables", "payables")
            ]
            if None not in parts:
                bfr = parts[0] + parts[1] - parts[2]
        ctx.metric(
            s,
            "working_funds_" + str(i),
            fr,
            "XOF",
            "Ressources stables − immobilisations, unité explicite",
            b.as_of,
            paths=[f"facts.balance_sheets.{i}"],
        )
        ctx.metric(
            s,
            "net_cash_" + str(i),
            None if fr is None or bfr is None else fr - bfr,
            "XOF",
            "Fonds de roulement − BFR à la même date ; indicateur de bilan, jamais déduit des flux directs",
            b.as_of,
        )
        ctx.metric(
            s,
            "current_liquidity_" + str(i),
            ratio(values["current_assets"], values["current_liabilities"]),
            "ratio",
            "Actifs circulants / passifs circulants strictement positifs",
            b.as_of,
        )
        s.data_used.append(
            DataUse(
                path=f"facts.balance_sheets.{i}",
                value=b.model_dump(mode="json"),
                period=b.as_of,
                unit="XOF × " + b.unit_multiplier,
                sources=[ctx.evidence[k] for k in b.evidence_ids],
            )
        )
    if not facts.balance_sheets:
        s.missing_information.append(
            "Postes de bilan comparables et unités pour fonds de roulement, trésorerie nette et liquidité."
        )
    for item in facts.aging:
        value = ctx.money(s, "aging." + item.reference, item.outstanding)
        overdue = None if item.due_date is None else max(0, (item.as_of - item.due_date).days)
        ctx.metric(
            s,
            "overdue_days_" + item.reference,
            overdue,
            "jours",
            "max(0, date de référence − échéance fournie)",
            item.as_of,
        )
        ctx.metric(
            s,
            "outstanding_" + item.reference,
            value,
            "XOF",
            "Solde restant fourni de la créance ou dette",
            item.as_of,
        )
        if overdue:
            s.alerts.append(
                f"{item.reference} : {overdue} jours de dépassement d’échéance à examiner."
            )
    return ctx.finish(
        s,
        "Postes et échéances fournis uniquement ; aucune transposition de ratios sans dénominateur cohérent.",
    )


def recurrent_share(case, facts):
    if not hasattr(case, "household_scope"):
        return {"status": "not_applicable"}
    classifications = {s.source: s.frequency for s in facts.source_classifications}
    reader = Context(case, None)
    totals = {"recurring": Decimal(0), "exceptional": Decimal(0)}
    unknown = False
    for p in case.periods:
        for income in p.incomes:
            value = reader.amount(income.net, "income_classification")
            kind = classifications.get(income.source, "unknown")
            if value is None or kind == "unknown":
                unknown = True
            else:
                totals[kind] += value
    total = sum(totals.values())
    return {
        "status": "incomplete" if unknown or total <= 0 else "available",
        "recurring_share": None if unknown or total <= 0 else totals["recurring"] / total,
        "exceptional_share": None if unknown or total <= 0 else totals["exceptional"] / total,
        "scope": "provided_sources_and_periods",
        "notice": "Classification déclarée explicite, sans garantie de continuité.",
    }
