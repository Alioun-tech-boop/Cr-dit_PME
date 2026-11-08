"""Niveau 3 — calculs institutionnels déterministes.

Fonctions pures sur des garanties, sinistres et paramètres de capacité.
Aucune donnée n'est inventée : une configuration absente produit un état
`not_configured` explicite plutôt qu'une valeur supposée.
"""

from decimal import Decimal, localcontext, ROUND_HALF_UP

from credit.intelligence import INSTITUTIONAL_RULES_VERSION

ZERO = Decimal(0)
CENT = Decimal("0.01")
RATIO = Decimal("0.00000001")
ACTIVE_STATUSES = {"approved", "transmitted", "active", "mobilized"}
CLOSED_STATUSES = {"closed", "expired", "rejected"}


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


def amount_of(item):
    return dec(item.get("approved_amount")) if item.get("approved_amount") is not None else dec(item.get("requested_amount"))


def capacity_summary(config, guarantees, claims=None):
    active = [g for g in guarantees if g.get("status") in ACTIVE_STATUSES]
    active_amount = sum((amount_of(g) or ZERO for g in active), ZERO)
    if config is None:
        return {
            "status": "not_configured",
            "as_of": None,
            "own_funds": None,
            "eligible_resources": None,
            "configured_cap": None,
            "active_commitments": text(active_amount),
            "remaining_capacity": None,
            "utilization": None,
            "coverage_limit": None,
            "alerts": [
                "Capacité institutionnelle non configurée : aucun plafond ne peut être calculé.",
            ],
            "notice": "Renseigner les fonds propres, ressources mobilisables et plafonds validés.",
        }
    own = dec(config.get("own_funds"))
    mobilizable = dec(config.get("mobilizable_resources"))
    liquid = dec(config.get("liquidities"))
    provisions = dec(config.get("provisions"))
    safety = dec(config.get("safety_reserve"))
    coverage = dec(config.get("coverage_limit"))
    eligible = None
    if own is not None:
        eligible = (
            own
            + (mobilizable or ZERO)
            + (liquid or ZERO)
            - (provisions or ZERO)
            - (safety or ZERO)
        )
    cap = dec(config.get("max_global_exposure"))
    if cap is None and eligible is not None and coverage is not None:
        cap = (eligible * coverage).quantize(CENT)
    remaining = None if cap is None else (cap - active_amount).quantize(CENT)
    utilization = ratio(active_amount, cap)
    expected_claims = ZERO
    for claim in claims or []:
        approved = dec(claim.get("approved_amount"))
        paid = dec(claim.get("paid_amount")) or ZERO
        recovered = dec(claim.get("recovered_amount")) or ZERO
        if approved is not None:
            expected_claims += max(ZERO, approved - paid - recovered)
    alerts = []
    if remaining is not None and remaining < 0:
        alerts.append("Dépassement du plafond d’engagement global.")
    if utilization is not None and utilization > Decimal("0.90"):
        alerts.append("Utilisation du plafond supérieure à 90 %.")
    if expected_claims > 0 and eligible is not None and expected_claims > eligible * Decimal("0.10"):
        alerts.append("Sinistres potentiels supérieurs à 10 % des ressources éligibles.")
    return {
        "status": "configured",
        "as_of": config.get("as_of"),
        "own_funds": text(own),
        "mobilizable_resources": text(mobilizable),
        "liquidities": text(liquid),
        "provisions": text(provisions),
        "safety_reserve": text(safety),
        "eligible_resources": text(eligible),
        "coverage_limit": text(coverage, 6),
        "configured_cap": text(cap),
        "active_commitments": text(active_amount),
        "remaining_capacity": text(remaining),
        "utilization": text(utilization),
        "expected_claims": text(expected_claims),
        "alerts": alerts,
        "formula": (
            "ressources éligibles = fonds propres + ressources mobilisables + liquidités "
            "− provisions − réserve de sécurité ; plafond = max_global_exposure ou "
            "ressources éligibles × limite de couverture ; capacité restante = plafond − engagements actifs."
        ),
        "notice": (
            "Les liquidités ne sont jamais assimilées à des ressources entièrement engageables. "
            "Une configuration absente n’est pas remplacée par une valeur supposée."
        ),
    }


def _group(guarantees, key):
    groups = {}
    for g in guarantees:
        name = g.get(key) or "non_renseigné"
        bucket = groups.setdefault(name, {"key": name, "count": 0, "amount": ZERO})
        bucket["count"] += 1
        bucket["amount"] += amount_of(g) or ZERO
    total = sum((b["amount"] for b in groups.values()), ZERO)
    return sorted(
        [
            {
                "key": b["key"],
                "count": b["count"],
                "amount": text(b["amount"]),
                "share": text(ratio(b["amount"], total)),
            }
            for b in groups.values()
        ],
        key=lambda x: Decimal(x["amount"] or "0"),
        reverse=True,
    )


def portfolio_metrics(guarantees, claims=None):
    total = sum((amount_of(g) or ZERO for g in guarantees), ZERO)
    active = [g for g in guarantees if g.get("status") in ACTIVE_STATUSES]
    active_amount = sum((amount_of(g) or ZERO for g in active), ZERO)
    status_groups = _group(guarantees, "status")
    banks = _group(guarantees, "partner_id")
    sectors = _group(guarantees, "sector")
    regions = _group(guarantees, "region")
    borrower_types = _group(guarantees, "borrower_type")
    risk_groups = _group(guarantees, "risk_level")
    high_risk = [g for g in guarantees if g.get("risk_level") in {"high", "critical"}]
    high_risk_amount = sum((amount_of(g) or ZERO for g in high_risk), ZERO)
    claims = claims or []
    declared_claims = sum((dec(c.get("declared_amount")) or ZERO for c in claims), ZERO)
    approved_claims = sum((dec(c.get("approved_amount")) or ZERO for c in claims), ZERO)
    paid_claims = sum((dec(c.get("paid_amount")) or ZERO for c in claims), ZERO)
    recovered_claims = sum((dec(c.get("recovered_amount")) or ZERO for c in claims), ZERO)
    largest_borrower = _group(guarantees, "case_id")[:1]
    largest_bank = banks[:1]
    largest_sector = sectors[:1]
    indicators = [
        {
            "id": "total_granted",
            "label": "Garanties accordées",
            "value": text(total),
            "unit": "XOF",
            "formula": "somme des montants garantis enregistrés",
            "level": "information",
        },
        {
            "id": "active_commitments",
            "label": "Engagements actifs",
            "value": text(active_amount),
            "unit": "XOF",
            "formula": "somme des garanties approuvées, transmises, actives ou mobilisées",
            "level": "information",
        },
        {
            "id": "high_risk_amount",
            "label": "Garanties à risque élevé",
            "value": text(high_risk_amount),
            "unit": "XOF",
            "formula": "somme des garanties classées high ou critical",
            "level": "high" if high_risk_amount > 0 else "low",
        },
        {
            "id": "declared_claims",
            "label": "Sinistres déclarés",
            "value": text(declared_claims),
            "unit": "XOF",
            "formula": "somme des montants déclarés",
            "level": "high" if declared_claims > 0 else "low",
        },
        {
            "id": "approved_claims",
            "label": "Sinistres approuvés",
            "value": text(approved_claims),
            "unit": "XOF",
            "formula": "somme des montants approuvés",
            "level": "high" if approved_claims > 0 else "low",
        },
        {
            "id": "recovered_claims",
            "label": "Recouvrements",
            "value": text(recovered_claims),
            "unit": "XOF",
            "formula": "somme des montants recouvrés",
            "level": "information",
        },
    ]
    alerts = []
    if largest_borrower and largest_borrower[0]["share"] is not None and dec(largest_borrower[0]["share"]) > Decimal("0.25"):
        alerts.append("Concentration emprunteur supérieure à 25 %.")
    if largest_bank and largest_bank[0]["share"] is not None and dec(largest_bank[0]["share"]) > Decimal("0.50"):
        alerts.append("Concentration bancaire supérieure à 50 %.")
    if largest_sector and largest_sector[0]["share"] is not None and dec(largest_sector[0]["share"]) > Decimal("0.40"):
        alerts.append("Concentration sectorielle supérieure à 40 %.")
    if total > 0 and ratio(high_risk_amount, total) is not None and dec(ratio(high_risk_amount, total)) > Decimal("0.20"):
        alerts.append("Plus de 20 % du portefeuille est classé à risque élevé.")
    return {
        "rules_version": INSTITUTIONAL_RULES_VERSION,
        "totals": {
            "granted": text(total),
            "active": text(active_amount),
            "high_risk": text(high_risk_amount),
            "declared_claims": text(declared_claims),
            "approved_claims": text(approved_claims),
            "paid_claims": text(paid_claims),
            "recovered_claims": text(recovered_claims),
        },
        "by_status": status_groups,
        "by_bank": banks,
        "by_sector": sectors,
        "by_region": regions,
        "by_borrower_type": borrower_types,
        "by_risk_level": risk_groups,
        "concentration": {
            "largest_borrower": largest_borrower[0] if largest_borrower else None,
            "largest_bank": largest_bank[0] if largest_bank else None,
            "largest_sector": largest_sector[0] if largest_sector else None,
        },
        "indicators": indicators,
        "alerts": alerts,
        "notice": "Indicateurs calculés sur les garanties et sinistres enregistrés ; aucun taux de défaut historique n’est supposé.",
    }


def stress_test(config, guarantees, scenarios):
    base = capacity_summary(config, guarantees)
    coverage = dec((config or {}).get("coverage_limit"))
    coverage = coverage if coverage is not None else Decimal(1)
    active = [g for g in guarantees if g.get("status") in ACTIVE_STATUSES]
    active_amount = sum((amount_of(g) or ZERO for g in active), ZERO)
    eligible = dec(base.get("eligible_resources"))
    cap = dec(base.get("configured_cap"))
    results = []
    for scenario in scenarios:
        kind = scenario.get("kind")
        impact = ZERO
        detail = ""
        if kind == "default_rate_increase":
            rate = dec(scenario.get("default_rate")) or ZERO
            impact = (active_amount * rate * coverage).quantize(CENT)
            detail = f"{text(rate * 100)} % des engagements actifs deviennent des sinistres."
        elif kind == "simultaneous_default":
            ids = set(scenario.get("guarantee_ids") or [])
            selected = [g for g in active if g.get("id") in ids] if ids else []
            if not selected and scenario.get("count"):
                selected = sorted(active, key=lambda g: amount_of(g) or ZERO, reverse=True)[
                    : int(scenario["count"])
                ]
            impact = sum((amount_of(g) or ZERO for g in selected), ZERO) * coverage
            detail = f"Défaillance simultanée de {len(selected)} garantie(s)."
        elif kind == "sector_degradation":
            sector = scenario.get("sector")
            share = dec(scenario.get("share")) or ZERO
            sector_amount = sum(
                (amount_of(g) or ZERO for g in active if g.get("sector") == sector), ZERO
            )
            impact = (sector_amount * share * coverage).quantize(CENT)
            detail = f"Dégradation du secteur {sector or 'non renseigné'} à hauteur de {text(share * 100)} %."
        elif kind == "concentration":
            largest = max((amount_of(g) or ZERO for g in active), default=ZERO)
            share = dec(scenario.get("share")) or Decimal(1)
            impact = (largest * share * coverage).quantize(CENT)
            detail = "Choc sur le plus grand emprunteur actif."
        elif kind == "mobilization":
            share = dec(scenario.get("share")) or ZERO
            impact = (active_amount * share * coverage).quantize(CENT)
            detail = f"Mobilisation de {text(share * 100)} % des engagements actifs."
        elif kind == "resource_degradation":
            reduction = dec(scenario.get("resource_reduction")) or ZERO
            if eligible is not None:
                impact = (eligible * reduction * (coverage if cap is None else Decimal(1))).quantize(CENT)
            detail = f"Dégradation des ressources éligibles de {text(reduction * 100)} %."
        post_cap = None if cap is None else cap
        post_remaining = None if post_cap is None else (post_cap - active_amount - impact).quantize(CENT)
        post_utilization = ratio(active_amount + impact, post_cap) if post_cap else None
        results.append(
            {
                **scenario,
                "impact_amount": text(impact),
                "post_stress_commitments": text(active_amount + impact),
                "post_stress_remaining_capacity": text(post_remaining),
                "post_stress_utilization": text(post_utilization),
                "breach": post_remaining is not None and post_remaining < 0,
                "detail": detail,
                "status": "computed" if base["status"] == "configured" else "not_configured",
            }
        )
    return {
        "rules_version": INSTITUTIONAL_RULES_VERSION,
        "base": base,
        "scenarios": results,
        "notice": "Stress tests déterministes sur les engagements enregistrés ; aucune probabilité de défaut n’est calibrée.",
    }


def claim_summary(claims):
    claims = claims or []
    totals = {
        "declared": sum((dec(c.get("declared_amount")) or ZERO for c in claims), ZERO),
        "received": sum((dec(c.get("received_amount")) or ZERO for c in claims), ZERO),
        "approved": sum((dec(c.get("approved_amount")) or ZERO for c in claims), ZERO),
        "paid": sum((dec(c.get("paid_amount")) or ZERO for c in claims), ZERO),
        "recovered": sum((dec(c.get("recovered_amount")) or ZERO for c in claims), ZERO),
    }
    outstanding = max(ZERO, totals["approved"] - totals["paid"] - totals["recovered"])
    by_status = {}
    for claim in claims:
        status = claim.get("status") or "unknown"
        by_status[status] = by_status.get(status, 0) + 1
    return {
        "count": len(claims),
        "totals": {k: text(v) for k, v in totals.items()},
        "outstanding": text(outstanding),
        "by_status": by_status,
        "notice": "Les montants déclarés, reçus, approuvés, payés et recouvrés restent distincts.",
    }
