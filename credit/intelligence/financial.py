"""Niveau 1 — intelligence financière déterministe.

Le module ne recalcule pas les flux : il exploite le rapport `financial_analysis_v2`
déjà stocké (sections, calculs, historique) et en dérive une lecture agrégée,
un score explicable sur 100, une complétude et des risques déterministes.
Aucune probabilité de défaut n'est produite.
"""

from decimal import Decimal, localcontext, ROUND_HALF_UP

from credit.intelligence import FINANCIAL_RULES_VERSION

ZERO = Decimal(0)
CENT = Decimal("0.01")
RATIO = Decimal("0.00000001")


def dec(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return None


def text(value, places=2):
    if value is None:
        return None
    with localcontext() as ctx:
        ctx.prec = 48
        ctx.rounding = ROUND_HALF_UP
        return str(Decimal(value).quantize(Decimal(1).scaleb(-places)))


def ratio(numerator, denominator):
    if numerator is None or denominator is None or denominator <= 0:
        return None
    with localcontext() as ctx:
        ctx.prec = 48
        ctx.rounding = ROUND_HALF_UP
        return (numerator / denominator).quantize(RATIO)


def strict_min(values):
    values = [v for v in values]
    if not values or any(v is None for v in values):
        return None
    return min(values)


def strict_max(values):
    values = [v for v in values]
    if not values or any(v is None for v in values):
        return None
    return max(values)


def linear(value, full_at, zero_at, higher_better=True):
    """Note linéaire 0–100 entre deux bornes documentées."""
    if value is None:
        return None
    value, full_at, zero_at = Decimal(value), Decimal(full_at), Decimal(zero_at)
    if higher_better:
        if value >= full_at:
            return Decimal(100)
        if value <= zero_at:
            return Decimal(0)
        return ((value - zero_at) / (full_at - zero_at) * 100).quantize(CENT)
    if value <= full_at:
        return Decimal(100)
    if value >= zero_at:
        return Decimal(0)
    return ((zero_at - value) / (zero_at - full_at) * 100).quantize(CENT)


def indicator(sections, id):
    for section in sections:
        for item in section.get("indicators", []):
            if item.get("id") == id:
                return dec(item.get("value")), item
    return None, None


def indicator_values(sections, prefix):
    values = []
    for section in sections:
        for item in section.get("indicators", []):
            if str(item.get("id", "")).startswith(prefix):
                values.append(dec(item.get("value")))
    return values


def case_amount(node):
    if isinstance(node, dict) and "value" in node:
        return dec(node.get("value"))
    return dec(node)


def period_rows(report):
    financial = report.get("financial_calculations") or {}
    return financial.get("periods") or []


def row_value(row, *keys):
    for key in keys:
        if key in row:
            return dec(row.get(key))
    return None


def repayment_reading(case):
    details = case.get("analysis_details") or {}
    observations = details.get("repayment_observations") or []
    if not observations:
        return {
            "available": False,
            "worst_days_past_due": None,
            "arrears_total": None,
            "restructuring_count": None,
            "points": None,
            "reason": "Aucun historique de remboursement fourni ; critère non noté.",
        }
    days = [o.get("days_past_due") for o in observations if o.get("days_past_due") is not None]
    arrears = [case_amount(o.get("arrears")) for o in observations]
    restructures = [
        o.get("restructuring_count")
        for o in observations
        if o.get("restructuring_count") is not None
    ]
    worst_days = max(days) if days else 0
    arrears_total = (
        sum((a for a in arrears if a is not None), ZERO) if any(a is not None for a in arrears) else None
    )
    restructure_total = sum(restructures) if restructures else 0
    if worst_days > 90:
        points = Decimal(0)
    elif worst_days > 30:
        points = Decimal(25)
    elif worst_days > 0:
        points = Decimal(60)
    else:
        points = Decimal(100)
    if restructure_total:
        points = max(ZERO, points - Decimal(20) * Decimal(restructure_total))
    return {
        "available": True,
        "worst_days_past_due": worst_days,
        "arrears_total": text(arrears_total),
        "restructuring_count": restructure_total,
        "points": text(points),
        "reason": "Historique de remboursement déclaré, non assimilé à une probabilité.",
    }


def criterion(id, label, value, unit, formula, weight, points, interpretation, justification):
    return {
        "id": id,
        "label": label,
        "value": text(value) if unit in {"XOF", "ratio", "mois"} else value,
        "unit": unit,
        "formula": formula,
        "weight": text(weight, 4),
        "points": text(points) if points is not None else None,
        "available": points is not None,
        "interpretation": interpretation,
        "justification": justification,
        "critical": id
        in {
            "debt_service_ratio",
            "min_margin_ratio",
            "dscr",
            "cash_months",
        },
    }


def band(score):
    if score is None:
        return {
            "id": "not_available",
            "label": "Non disponible",
            "risk_level": "unknown",
        }
    if score >= Decimal(80):
        return {"id": "solid", "label": "Solide", "risk_level": "low"}
    if score >= Decimal(65):
        return {"id": "satisfactory", "label": "Satisfaisant", "risk_level": "low"}
    if score >= Decimal(50):
        return {"id": "watch", "label": "À surveiller", "risk_level": "moderate"}
    if score >= Decimal(35):
        return {"id": "fragile", "label": "Fragile", "risk_level": "high"}
    return {"id": "critical", "label": "Critique", "risk_level": "critical"}


def _individual_criteria(report, case, rows):
    income = [row_value(r, "net_retained_income") for r in rows]
    available = [row_value(r, "available_before_debt") for r in rows]
    existing = [row_value(r, "existing_debt_service") for r in rows]
    new = [row_value(r, "new_debt_service") for r in rows]
    margins = [row_value(r, "margin_after_credit", "margin_after_debt") for r in rows]
    reserves = [row_value(r, "projected_reserve", "closing_cash") for r in rows]

    latest_income = next((v for v in reversed(income) if v is not None), None)
    latest_available = next((v for v in reversed(available) if v is not None), None)
    latest_existing = next((v for v in reversed(existing) if v is not None), None)
    latest_new = next((v for v in reversed(new) if v is not None), None)
    total_service = (
        None if latest_existing is None or latest_new is None else latest_existing + latest_new
    )
    essential = (
        None if latest_income is None or latest_available is None else latest_income - latest_available
    )
    debt_ratio = ratio(total_service, latest_income)
    min_margin = strict_min(margins)
    min_margin_ratio = ratio(min_margin, latest_income)
    min_reserve = strict_min(reserves)
    capacity = strict_min(
        [
            None if a is None or e is None else a - e
            for a, e in zip(available, existing)
        ]
    )
    expenses = [
        None if i is None or a is None else i - a for i, a in zip(income, available)
    ]
    max_expense = strict_max(expenses)
    reserve = case_amount(case.get("mobilizable_reserve"))
    reserve_months = ratio(reserve, max_expense)
    findings = (report.get("financial_calculations") or {}).get("financial_findings") or {}
    history = (report.get("deep_analysis") or {}).get("history") or {}
    cv = dec(findings.get("income_variability_cv")) or dec(history.get("coefficient_of_variation"))
    concentration, _ = indicator(report.get("sections") or [], "largest_source_share")
    repayment = repayment_reading(case)

    return {
        "income": latest_income,
        "essential": essential,
        "existing_service": latest_existing,
        "new_service": latest_new,
        "total_service": total_service,
        "debt_ratio": debt_ratio,
        "min_margin": min_margin,
        "min_margin_ratio": min_margin_ratio,
        "min_reserve": min_reserve,
        "capacity": capacity,
        "reserve": reserve,
        "reserve_months": reserve_months,
        "income_cv": cv,
        "concentration": concentration,
        "repayment": repayment,
        "criteria": [
            criterion(
                "debt_service_ratio",
                "Poids des échéances",
                debt_ratio,
                "ratio",
                "(échéances existantes + nouvelle échéance) / revenus nets retenus",
                Decimal("0.20"),
                linear(debt_ratio, Decimal("0.30"), Decimal("0.60"), higher_better=False),
                "Un ratio faible laisse une marge de manœuvre.",
                "Comparaison des échéances aux revenus nets retenus de la dernière période.",
            ),
            criterion(
                "min_margin_ratio",
                "Marge résiduelle minimale",
                min_margin_ratio,
                "ratio",
                "minimum des marges après crédit / revenus nets retenus",
                Decimal("0.20"),
                linear(min_margin_ratio, Decimal("0.15"), Decimal("0.00"), higher_better=True),
                "Une marge positive et significative absorbe un imprévu.",
                "La plus faible marge de toutes les périodes fournies est retenue.",
            ),
            criterion(
                "reserve_months",
                "Réserve mobilisable",
                reserve_months,
                "mois",
                "réserve mobilisable / dépenses essentielles maximales d’une période",
                Decimal("0.15"),
                linear(reserve_months, Decimal("3"), Decimal("0"), higher_better=True),
                "Trois mois de dépenses constituent un repère prudent, non une norme.",
                "L’épargne bloquée est exclue du disponible.",
            ),
            criterion(
                "income_stability",
                "Stabilité des revenus",
                cv,
                "ratio",
                "écart type de population / moyenne des revenus historiques comparables",
                Decimal("0.15"),
                linear(cv, Decimal("0.10"), Decimal("0.50"), higher_better=False),
                "Un revenu régulier réduit l’incertitude de remboursement.",
                "Calcul sur l’historique fourni uniquement, sans extrapolation.",
            ),
            criterion(
                "income_concentration",
                "Concentration des revenus",
                concentration,
                "ratio",
                "revenu de la première source / revenus nets totaux de la période",
                Decimal("0.10"),
                linear(concentration, Decimal("0.50"), Decimal("1.00"), higher_better=False),
                "Une dépendance forte à une source unique fragilise le dossier.",
                "Une seule source déclarée est signalée comme dépendance.",
            ),
            criterion(
                "expense_ratio",
                "Poids des charges essentielles",
                ratio(essential, latest_income),
                "ratio",
                "dépenses essentielles / revenus nets retenus",
                Decimal("0.10"),
                linear(ratio(essential, latest_income), Decimal("0.50"), Decimal("0.90"), higher_better=False),
                "Des charges contenues libèrent de la capacité.",
                "Les dépenses essentielles ne sont jamais réduites pour améliorer le score.",
            ),
            criterion(
                "repayment_history",
                "Historique de remboursement",
                repayment["worst_days_past_due"],
                "jours",
                "retard maximal observé et restructurations déclarées",
                Decimal("0.10"),
                dec(repayment["points"]),
                "L’absence d’incident déclaré est favorable sans être une garantie.",
                repayment["reason"],
            ),
        ],
        "groups": [
            {
                "id": "income",
                "label": "Revenus",
                "items": [
                    _item("Revenus nets retenus", latest_income, "XOF", "somme des revenus nets retenus"),
                    _item("Variabilité historique", cv, "ratio", "écart type / moyenne"),
                    _item("Première source", concentration, "ratio", "part de la première source"),
                ],
            },
            {
                "id": "expenses",
                "label": "Charges",
                "items": [
                    _item("Dépenses essentielles", essential, "XOF", "revenus nets − disponible avant dettes"),
                    _item("Poids des charges", ratio(essential, latest_income), "ratio", "charges / revenus"),
                ],
            },
            {
                "id": "debt",
                "label": "Dettes",
                "items": [
                    _item("Échéances existantes", latest_existing, "XOF", "service des dettes existantes"),
                    _item("Nouvelle échéance", latest_new, "XOF", "service du crédit demandé"),
                    _item("Taux d’endettement", debt_ratio, "ratio", "échéances / revenus"),
                ],
            },
            {
                "id": "savings",
                "label": "Épargne et réserve",
                "items": [
                    _item("Réserve mobilisable", reserve, "XOF", "épargne disponible hors épargne bloquée"),
                    _item("Mois de réserve", reserve_months, "mois", "réserve / charges maximales"),
                    _item("Réserve minimale projetée", min_reserve, "XOF", "minimum des soldes projetés"),
                ],
            },
            {
                "id": "capacity",
                "label": "Capacité de remboursement",
                "items": [
                    _item("Capacité mensuelle avant nouveau crédit", capacity, "XOF", "disponible avant dettes − échéances existantes"),
                    _item("Marge minimale après crédit", min_margin, "XOF", "minimum des marges après crédit"),
                ],
            },
        ],
    }


def _business_criteria(report, case, rows):
    receipts = [row_value(r, "operating_receipts") for r in rows]
    available = [row_value(r, "cash_available_for_debt") for r in rows]
    existing = [row_value(r, "existing_debt_service") for r in rows]
    new = [row_value(r, "new_debt_service") for r in rows]
    margins = [row_value(r, "margin_after_debt", "margin_after_credit") for r in rows]
    cash = [row_value(r, "closing_cash", "projected_reserve") for r in rows]
    coverage = [row_value(r, "debt_service_coverage") for r in rows]

    latest_receipts = next((v for v in reversed(receipts) if v is not None), None)
    latest_available = next((v for v in reversed(available) if v is not None), None)
    latest_existing = next((v for v in reversed(existing) if v is not None), None)
    latest_new = next((v for v in reversed(new) if v is not None), None)
    total_service = (
        None if latest_existing is None or latest_new is None else latest_existing + latest_new
    )
    dscr = strict_min(coverage)
    min_cash = strict_min(cash)
    min_margin = strict_min(margins)
    capacity = strict_min(
        [None if a is None or e is None else a - e for a, e in zip(available, existing)]
    )
    outflows = [
        None if r is None or a is None else r - a for r, a in zip(receipts, available)
    ]
    monthly_outflow = strict_max(outflows)
    cash_months = ratio(min_cash, monthly_outflow)
    debt_burden = ratio(total_service, latest_available)
    sections = report.get("sections") or []
    net_margin, _ = indicator(sections, "net_margin")
    growth, _ = indicator(sections, "turnover_growth")
    concentration, _ = indicator(sections, "largest_customer_share")
    working_capital, _ = indicator(sections, "working_capital")
    repayment = repayment_reading(case)
    findings = (report.get("financial_calculations") or {}).get("financial_findings") or {}
    history = (report.get("deep_analysis") or {}).get("history") or {}
    cv = dec(findings.get("income_variability_cv")) or dec(history.get("coefficient_of_variation"))

    return {
        "receipts": latest_receipts,
        "available": latest_available,
        "existing_service": latest_existing,
        "new_service": latest_new,
        "total_service": total_service,
        "dscr": dscr,
        "debt_burden": debt_burden,
        "min_cash": min_cash,
        "min_margin": min_margin,
        "cash_months": cash_months,
        "capacity": capacity,
        "net_margin": net_margin,
        "growth": growth,
        "concentration": concentration,
        "working_capital": working_capital,
        "income_cv": cv,
        "repayment": repayment,
        "criteria": [
            criterion(
                "dscr",
                "Couverture du service de la dette",
                dscr,
                "ratio",
                "trésorerie disponible pour la dette / service total de la dette",
                Decimal("0.24"),
                linear(dscr, Decimal("1.50"), Decimal("1.00"), higher_better=True),
                "Un DSCR supérieur à 1 couvre l’échéance ; 1,5 constitue une marge de sécurité.",
                "Le minimum de toutes les périodes fournies est retenu.",
            ),
            criterion(
                "net_margin",
                "Marge nette",
                net_margin,
                "ratio",
                "résultat net comptable / chiffre d’affaires",
                Decimal("0.16"),
                linear(net_margin, Decimal("0.10"), Decimal("0.00"), higher_better=True),
                "Une marge nette positive traduit une rentabilité effective.",
                "Indicateur comptable fourni, non déduit des seuls flux de caisse.",
            ),
            criterion(
                "turnover_growth",
                "Évolution du chiffre d’affaires",
                growth,
                "ratio",
                "(CA comparable après − CA comparable avant) / CA avant",
                Decimal("0.12"),
                linear(growth, Decimal("0.10"), Decimal("-0.10"), higher_better=True),
                "La croissance soutient la capacité future, sans la garantir.",
                "Comparaison de périodes de durées comparables uniquement.",
            ),
            criterion(
                "cash_months",
                "Trésorerie disponible",
                cash_months,
                "mois",
                "trésorerie minimale projetée / sorties mensuelles maximales",
                Decimal("0.16"),
                linear(cash_months, Decimal("1.50"), Decimal("0.00"), higher_better=True),
                "Une trésorerie de sécurité couvre les décalages d’encaissement.",
                "La trésorerie minimale de toutes les périodes est retenue.",
            ),
            criterion(
                "debt_burden",
                "Poids du service de la dette",
                debt_burden,
                "ratio",
                "service total de la dette / trésorerie disponible pour la dette",
                Decimal("0.14"),
                linear(debt_burden, Decimal("0.40"), Decimal("1.00"), higher_better=False),
                "Un poids faible laisse de la trésorerie pour l’exploitation.",
                "Complète le DSCR sans le remplacer.",
            ),
            criterion(
                "customer_concentration",
                "Concentration clients",
                concentration,
                "ratio",
                "encaissements du premier client / encaissements totaux rapprochés",
                Decimal("0.10"),
                linear(concentration, Decimal("0.30"), Decimal("1.00"), higher_better=False),
                "Une dépendance client forte expose l’activité à une perte unique.",
                "Calcul uniquement si la ventilation client est complète.",
            ),
            criterion(
                "repayment_history",
                "Historique de remboursement",
                repayment["worst_days_past_due"],
                "jours",
                "retard maximal observé et restructurations déclarées",
                Decimal("0.08"),
                dec(repayment["points"]),
                "L’absence d’incident déclaré est favorable sans être une garantie.",
                repayment["reason"],
            ),
        ],
        "groups": [
            {
                "id": "activity",
                "label": "Activité et rentabilité",
                "items": [
                    _item("Chiffre d’affaires", latest_receipts, "XOF", "encaissements d’exploitation retenus"),
                    _item("Croissance du CA", growth, "ratio", "évolution comparable"),
                    _item("Marge nette", net_margin, "ratio", "résultat net / CA"),
                ],
            },
            {
                "id": "treasury",
                "label": "Trésorerie",
                "items": [
                    _item("Trésorerie minimale", min_cash, "XOF", "minimum des soldes projetés"),
                    _item("Mois de trésorerie", cash_months, "mois", "trésorerie / sorties mensuelles"),
                    _item("Besoin en fonds de roulement", working_capital, "XOF", "stocks + créances − fournisseurs"),
                ],
            },
            {
                "id": "debt",
                "label": "Endettement",
                "items": [
                    _item("Service existant", latest_existing, "XOF", "échéances des dettes existantes"),
                    _item("Nouveau service", latest_new, "XOF", "échéance du crédit demandé"),
                    _item("Poids du service", debt_burden, "ratio", "service / trésorerie disponible"),
                ],
            },
            {
                "id": "coverage",
                "label": "Capacité de remboursement",
                "items": [
                    _item("DSCR minimal", dscr, "ratio", "trésorerie disponible / service total"),
                    _item("Capacité avant nouveau crédit", capacity, "XOF", "disponible − échéances existantes"),
                    _item("Marge minimale après dette", min_margin, "XOF", "minimum des marges"),
                ],
            },
            {
                "id": "concentration",
                "label": "Dépendances",
                "items": [
                    _item("Premier client", concentration, "ratio", "part du premier client"),
                    _item("Variabilité des encaissements", cv, "ratio", "écart type / moyenne"),
                ],
            },
        ],
    }


def _item(label, value, unit, formula):
    return {
        "label": label,
        "value": text(value) if unit in {"XOF", "ratio", "mois"} else value,
        "unit": unit,
        "formula": formula,
        "available": value is not None,
    }


def build_trends(report, rows, core):
    history = (report.get("deep_analysis") or {}).get("history") or {}
    income = [row_value(r, "net_retained_income", "operating_receipts") for r in rows]
    margins = [row_value(r, "margin_after_credit", "margin_after_debt") for r in rows]
    reserves = [row_value(r, "projected_reserve", "closing_cash") for r in rows]
    services = [
        None
        if row_value(r, "existing_debt_service") is None or row_value(r, "new_debt_service") is None
        else row_value(r, "existing_debt_service") + row_value(r, "new_debt_service")
        for r in rows
    ]

    def direction(values):
        known = [v for v in values if v is not None]
        if len(known) < 2:
            return "unknown"
        first, last = known[0], known[-1]
        if first == 0:
            return "up" if last > 0 else "stable"
        change = (last - first) / abs(first)
        if change > Decimal("0.05"):
            return "up"
        if change < Decimal("-0.05"):
            return "down"
        return "stable"

    points = []
    for index, row in enumerate(rows):
        points.append(
            {
                "period": row.get("period"),
                "income": text(income[index]),
                "margin": text(margins[index]),
                "reserve": text(reserves[index]),
                "debt_service": text(services[index]),
            }
        )
    cv = dec(history.get("coefficient_of_variation"))
    concentration = None
    sections = report.get("sections") or []
    concentration, _ = indicator(
        sections, "largest_source_share" if core == "individuals" else "largest_customer_share"
    )
    return {
        "points": points,
        "history": {
            "provided_periods": history.get("provided_periods"),
            "known_periods": history.get("known_periods"),
            "mean": text(dec(history.get("mean"))),
            "median": text(dec(history.get("median"))),
            "minimum": text(dec(history.get("minimum"))),
            "maximum": text(dec(history.get("maximum"))),
            "coefficient_of_variation": text(cv),
            "comparable_change": text(dec(history.get("comparable_change"))),
            "seasonality_status": history.get("seasonality_status"),
        },
        "directions": {
            "income": direction(income),
            "profitability": direction(margins),
            "debt": direction(services),
            "treasury": direction(reserves),
        },
        "irregularity": {
            "coefficient_of_variation": text(cv),
            "status": "high" if cv is not None and cv >= Decimal("0.30") else "moderate" if cv is not None and cv >= Decimal("0.15") else "low" if cv is not None else "unknown",
        },
        "dependence": {
            "share": text(concentration),
            "status": "high" if concentration is not None and concentration >= Decimal("0.60") else "moderate" if concentration is not None and concentration >= Decimal("0.40") else "low" if concentration is not None else "unknown",
        },
        "notice": "Évolutions descriptives sur les seules périodes fournies ; aucune extrapolation.",
    }


def build_risks(core, metrics, trends, score, score_status):
    risks = []

    def add(id, label, category, level, explanation, evidence, rule):
        risks.append(
            {
                "id": id,
                "label": label,
                "category": category,
                "level": level,
                "explanation": explanation,
                "evidence": evidence,
                "rule": rule,
            }
        )

    if core == "individuals":
        debt = metrics["debt_ratio"]
        if debt is not None:
            level = "critical" if debt >= Decimal("0.55") else "high" if debt >= Decimal("0.40") else "moderate" if debt >= Decimal("0.33") else "low"
            add(
                "overindebtedness",
                "Risque de surendettement",
                "debt",
                level,
                "Le poids des échéances dans les revenus nets retenus est de " + text(debt * 100) + " %.",
                [{"indicator": "debt_service_ratio", "value": text(debt)}],
                "debt_service_ratio ≥ 0,40 : élevé ; ≥ 0,55 : critique",
            )
        margin = metrics["min_margin"]
        if margin is not None:
            level = "critical" if margin < 0 else "high" if metrics["min_margin_ratio"] is not None and metrics["min_margin_ratio"] < Decimal("0.05") else "low"
            add(
                "repayment_capacity",
                "Risque d’incapacité de remboursement",
                "capacity",
                level,
                "La marge minimale après crédit est de " + text(margin) + " XOF sur les périodes fournies.",
                [{"indicator": "min_margin", "value": text(margin)}],
                "marge < 0 : critique ; marge/revenus < 5 % : élevé",
            )
        reserve = metrics["reserve_months"]
        if reserve is not None:
            level = "critical" if reserve <= 0 else "high" if reserve < 1 else "moderate" if reserve < 2 else "low"
            add(
                "liquidity",
                "Risque d’insuffisance de trésorerie",
                "treasury",
                level,
                "La réserve mobilisable couvre " + text(reserve) + " mois de dépenses essentielles.",
                [{"indicator": "reserve_months", "value": text(reserve)}],
                "< 1 mois : élevé ; < 2 mois : modéré",
            )
        income_direction = trends["directions"]["income"]
        cv = dec(trends["irregularity"]["coefficient_of_variation"])
        if income_direction == "down" or (cv is not None and cv >= Decimal("0.30")):
            add(
                "income_decline",
                "Risque de baisse ou d’irrégularité des revenus",
                "income",
                "high" if income_direction == "down" else "moderate",
                "Tendance des revenus : " + income_direction + " ; variabilité : " + text(cv) + ".",
                [{"indicator": "income_stability", "value": text(cv)}],
                "tendance baissière > 5 % ou CV ≥ 0,30",
            )
        concentration = dec(trends["dependence"]["share"])
        if concentration is not None and concentration >= Decimal("0.60"):
            add(
                "income_concentration",
                "Risque de concentration des revenus",
                "income",
                "high" if concentration >= Decimal("0.80") else "moderate",
                "La première source représente " + text(concentration * 100) + " % des revenus nets.",
                [{"indicator": "income_concentration", "value": text(concentration)}],
                "part ≥ 0,60 : modéré ; ≥ 0,80 : élevé",
            )
    else:
        dscr = metrics["dscr"]
        if dscr is not None:
            level = "critical" if dscr < 1 else "high" if dscr < Decimal("1.20") else "moderate" if dscr < Decimal("1.50") else "low"
            add(
                "debt_coverage",
                "Risque de couverture insuffisante de la dette",
                "debt",
                level,
                "Le DSCR minimal est de " + text(dscr) + " sur les périodes fournies.",
                [{"indicator": "dscr", "value": text(dscr)}],
                "DSCR < 1 : critique ; < 1,20 : élevé ; < 1,50 : modéré",
            )
        margin = metrics["net_margin"]
        if margin is not None:
            add(
                "profitability",
                "Risque de rentabilité insuffisante",
                "profitability",
                "high" if margin < 0 else "moderate" if margin < Decimal("0.03") else "low",
                "La marge nette comptable est de " + text(margin * 100) + " %.",
                [{"indicator": "net_margin", "value": text(margin)}],
                "marge nette < 0 : élevé",
            )
        cash = metrics["cash_months"]
        if cash is not None:
            level = "critical" if cash <= 0 else "high" if cash < Decimal("0.50") else "moderate" if cash < 1 else "low"
            add(
                "liquidity",
                "Risque d’insuffisance de trésorerie",
                "treasury",
                level,
                "La trésorerie minimale couvre " + text(cash) + " mois de sorties.",
                [{"indicator": "cash_months", "value": text(cash)}],
                "< 0,5 mois : élevé ; < 1 mois : modéré",
            )
        growth = metrics["growth"]
        if growth is not None and growth < 0:
            add(
                "activity_decline",
                "Risque de baisse d’activité",
                "activity",
                "high" if growth <= Decimal("-0.10") else "moderate",
                "Évolution du chiffre d’affaires comparable : " + text(growth * 100) + " %.",
                [{"indicator": "turnover_growth", "value": text(growth)}],
                "baisse > 10 % : élevé",
            )
        concentration = metrics["concentration"]
        if concentration is not None and concentration >= Decimal("0.40"):
            add(
                "customer_concentration",
                "Risque de concentration clients",
                "activity",
                "high" if concentration >= Decimal("0.60") else "moderate",
                "Le premier client représente " + text(concentration * 100) + " % des encaissements rapprochés.",
                [{"indicator": "customer_concentration", "value": text(concentration)}],
                "part ≥ 0,40 : modéré ; ≥ 0,60 : élevé",
            )
        working_capital = metrics["working_capital"]
        if working_capital is not None and working_capital < 0:
            add(
                "working_capital",
                "Risque de besoin en fonds de roulement",
                "treasury",
                "moderate",
                "Le besoin en fonds de roulement déclaré est négatif : " + text(working_capital) + " XOF.",
                [{"indicator": "working_capital", "value": text(working_capital)}],
                "BFR négatif à documenter",
            )

    margin_direction = trends["directions"]["profitability"]
    treasury_direction = trends["directions"]["treasury"]
    if margin_direction == "down" and treasury_direction == "down":
        add(
            "financial_deterioration",
            "Risque de dégradation financière",
            "trend",
            "high",
            "La marge et la trésorerie diminuent simultanément sur les périodes fournies.",
            [
                {"indicator": "margin_direction", "value": margin_direction},
                {"indicator": "treasury_direction", "value": treasury_direction},
            ],
            "deux tendances baissières simultanées",
        )

    if score_status != "available":
        add(
            "incomplete_data",
            "Données insuffisantes pour conclure",
            "quality",
            "high",
            "Le score financier n’est pas calculable avec une couverture suffisante.",
            [{"indicator": "score_status", "value": score_status}],
            "couverture des critères < 70 % ou critère critique indisponible",
        )
    if not risks:
        add(
            "no_major_financial_risk",
            "Aucun risque financier majeur identifié",
            "synthesis",
            "low",
            "Les indicateurs disponibles ne déclenchent aucune règle de vigilance.",
            [],
            "aucune règle défavorable déclenchée",
        )
    order = {"critical": 0, "high": 1, "moderate": 2, "low": 3}
    risks.sort(key=lambda r: order.get(r["level"], 4))
    return risks


def build_financial_intelligence(report, case):
    """Construit la lecture financière niveau 1 à partir d'un rapport v2 stocké."""
    core = report.get("core") or ("businesses" if "opening_cash" in case else "individuals")
    rows = period_rows(report)
    metrics = _individual_criteria(report, case, rows) if core == "individuals" else _business_criteria(report, case, rows)
    criteria = metrics["criteria"]
    available_weight = sum(
        (Decimal(c["weight"]) for c in criteria if c["points"] is not None), ZERO
    )
    total_weight = sum((Decimal(c["weight"]) for c in criteria), ZERO)
    coverage = ratio(available_weight, total_weight)
    critical_missing = any(c["critical"] and c["points"] is None for c in criteria)
    if coverage is not None and coverage >= Decimal("0.70") and not critical_missing:
        weighted = sum(
            (Decimal(c["weight"]) * Decimal(c["points"]) for c in criteria if c["points"] is not None),
            ZERO,
        )
        score = (weighted / available_weight).quantize(CENT)
        score_status = "available"
    else:
        score = None
        score_status = "incomplet"
    interpretation = band(score)
    trends = build_trends(report, rows, core)
    risks = build_risks(core, metrics, trends, score, score_status)
    favorable = [c for c in criteria if c["points"] is not None and Decimal(c["points"]) >= Decimal("70")]
    unfavorable = [c for c in criteria if c["points"] is not None and Decimal(c["points"]) < Decimal("50")]
    missing = [
        {
            "criterion": c["id"],
            "label": c["label"],
            "reason": "Valeur indisponible dans le rapport source.",
        }
        for c in criteria
        if c["points"] is None
    ]
    return {
        "rules_version": FINANCIAL_RULES_VERSION,
        "core": core,
        "score": {
            "value": text(score),
            "status": score_status,
            "band": interpretation["id"],
            "label": interpretation["label"],
            "risk_level": interpretation["risk_level"],
            "coverage": text(coverage),
            "available_weight": text(available_weight, 4),
            "total_weight": text(total_weight, 4),
            "formula": "Σ (poids × note du critère) / Σ poids disponibles",
            "notice": "Score conventionnel explicable, non une probabilité de défaut.",
        },
        "criteria": criteria,
        "favorable": [
            {"id": c["id"], "label": c["label"], "points": c["points"]}
            for c in favorable
        ],
        "unfavorable": [
            {"id": c["id"], "label": c["label"], "points": c["points"]}
            for c in unfavorable
        ],
        "missing_criteria": missing,
        "groups": metrics["groups"],
        "trends": trends,
        "risks": risks,
        "default_risk": {
            "method": "deterministic_indicator_rules",
            "probability_of_default": None,
            "calibrated": False,
            "statement": (
                "Évaluation déterministe du risque à partir des indicateurs financiers. "
                "Aucune probabilité statistique calibrée n’est calculée ni affichée."
            ),
            "risk_level": interpretation["risk_level"],
            "drivers": [r["label"] for r in risks if r["level"] in {"high", "critical"}],
        },
        "capacity": {
            "monthly_before_new_debt": text(metrics["capacity"]),
            "minimum_margin_after_debt": text(metrics["min_margin"]),
            "debt_service": text(metrics["total_service"]),
            "income": text(metrics.get("income", metrics.get("receipts"))),
        },
    }
