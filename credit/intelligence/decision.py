"""Niveau 2 — intelligence décisionnelle déterministe.

Exploite la lecture financière niveau 1 et le rapport source. Ne recalcule pas
les indicateurs financiers : il agrège la fiabilité, la faisabilité du
financement, les scénarios et produit une recommandation de garantie explicable.
"""

from datetime import date
from decimal import Decimal, localcontext, ROUND_HALF_UP

from credit.intelligence import DECISION_RULES_VERSION

ZERO = Decimal(0)
CENT = Decimal("0.01")
RATIO = Decimal("0.00000001")

OUTCOME_LABELS = {
    "favorable": "Favorable",
    "favorable_sous_conditions": "Favorable sous conditions",
    "analyse_complementaire_necessaire": "Analyse complémentaire nécessaire",
    "defavorable": "Défavorable",
}


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


def annuity_principal(instalment, annual_rate, months):
    if instalment is None or months is None or months <= 0:
        return None
    rate = ZERO if annual_rate is None else Decimal(annual_rate) / Decimal(12)
    with localcontext() as ctx:
        ctx.prec = 48
        ctx.rounding = ROUND_HALF_UP
        if rate == 0:
            return (instalment * Decimal(months)).quantize(CENT)
        factor = (Decimal(1) - (Decimal(1) + rate) ** (-Decimal(months))) / rate
        return (instalment * factor).quantize(CENT)


def build_reliability(report, case, intelligence, today=None):
    today = today or date.today()
    details = case.get("analysis_details") or {}
    evidence = case.get("evidence") or []
    contradictory = [e for e in evidence if e.get("status") == "contradictory"]
    missing_evidence = [e for e in evidence if e.get("status") == "missing"]
    verified = [e for e in evidence if e.get("status") == "verified"]
    declared = [e for e in evidence if e.get("status") == "declared"]
    unverified = [e for e in evidence if e.get("status") == "unverified_extracted"]
    missing_information = list(report.get("missing_information") or [])
    reconciliation = (report.get("deep_analysis") or {}).get("reconciliation") or {}
    checks = reconciliation.get("checks") or []
    warnings = reconciliation.get("warnings") or []
    coverage = reconciliation.get("coverage") or {}
    important = coverage.get("important_amounts")
    unknown = coverage.get("unknown_amounts")
    unknown_ratio = ratio(Decimal(unknown), Decimal(important)) if important else None
    as_of = details.get("as_of")
    age_days = None
    if as_of:
        try:
            age_days = (today - date.fromisoformat(str(as_of))).days
        except ValueError:
            age_days = None
    failed_checks = [c for c in checks if c.get("status") not in {"matched", "not_applicable"}]
    contradictions = list((details.get("identity") or {}).get("contradictions") or [])
    human_verifications = list(missing_information)
    if contradictory:
        human_verifications.append(
            "Pièces contradictoires à vérifier : " + ", ".join(e.get("id", "") for e in contradictory)
        )
    if failed_checks:
        human_verifications.append(
            "Rapprochements non concordants : " + ", ".join(c.get("id", "") for c in failed_checks)
        )

    reasons = []
    if contradictory or contradictions:
        level = "critical"
        reasons.append("Contradictions documentaires ou d’identité déclarées.")
    elif intelligence["score"]["status"] != "available":
        level = "incomplete"
        reasons.append("Indicateurs critiques ou couverture insuffisante pour un score fiable.")
    elif unknown_ratio is not None and unknown_ratio > Decimal("0.30"):
        level = "incomplete"
        reasons.append("Plus de 30 % des montants importants sont inconnus.")
    elif age_days is not None and age_days > 180:
        level = "incomplete"
        reasons.append("Données de référence âgées de plus de 180 jours.")
    elif failed_checks:
        level = "incomplete"
        reasons.append("Des rapprochements comptables ne concordent pas.")
    elif missing_information:
        level = "adequate_with_reserves"
        reasons.append("Des informations complémentaires restent demandées.")
    else:
        level = "adequate"
        reasons.append("Aucune contradiction bloquante détectée dans les données fournies.")

    return {
        "level": level,
        "label": {
            "adequate": "Dossier fiable",
            "adequate_with_reserves": "Fiable avec réserves",
            "incomplete": "Dossier incomplet",
            "critical": "Dossier suspendu",
        }[level],
        "suspended": level == "critical",
        "can_proceed": level != "critical",
        "reasons": reasons,
        "components": [
            {
                "id": "completeness",
                "label": "Complétude des informations",
                "status": "incomplete" if missing_information else "complete",
                "detail": f"{len(missing_information)} élément(s) à compléter.",
                "items": missing_information[:50],
            },
            {
                "id": "coherence",
                "label": "Cohérence des données",
                "status": "incomplete" if failed_checks else "complete",
                "detail": f"{len(failed_checks)} rapprochement(s) non concordant(s).",
                "items": [str(c.get("id")) for c in failed_checks],
            },
            {
                "id": "documents",
                "label": "Présence et statut des justificatifs",
                "status": "critical" if contradictory else "incomplete" if missing_evidence else "complete",
                "detail": (
                    f"{len(verified)} vérifié(s), {len(declared)} déclaré(s), "
                    f"{len(unverified)} extrait(s) non contrôlé(s), {len(contradictory)} contradictoire(s), "
                    f"{len(missing_evidence)} manquant(s)."
                ),
                "items": [],
            },
            {
                "id": "financial_reliability",
                "label": "Fiabilité des informations financières",
                "status": "incomplete" if unknown_ratio is not None and unknown_ratio > Decimal("0.30") else "complete",
                "detail": (
                    "Montants importants inconnus : "
                    + (text(unknown_ratio * 100) + " %" if unknown_ratio is not None else "non mesurable")
                ),
                "items": warnings[:50],
            },
            {
                "id": "freshness",
                "label": "Ancienneté des informations",
                "status": "incomplete" if age_days is not None and age_days > 180 else "complete",
                "detail": (f"Date de référence : {as_of} ; ancienneté : {age_days} jour(s)." if as_of else "Date de référence non renseignée."),
                "items": [],
            },
            {
                "id": "human_review",
                "label": "Éléments nécessitant une vérification humaine",
                "status": "required" if human_verifications else "not_required",
                "detail": f"{len(human_verifications)} vérification(s) humaine(s) requise(s).",
                "items": human_verifications[:50],
            },
        ],
        "human_verifications": human_verifications,
        "notice": "La fiabilité porte sur les pièces et déclarations fournies ; aucune authentification externe n’est affirmée.",
    }


def _scenario_view(item, expected_id, label):
    if not item:
        return {
            "id": expected_id,
            "label": label,
            "status": "not_available",
            "min_margin": None,
            "min_reserve": None,
            "reason": "Scénario non exécuté dans l’analyse source.",
        }
    return {
        "id": expected_id,
        "label": label,
        "status": item.get("status", "available"),
        "min_margin": item.get("min_margin"),
        "min_reserve": item.get("min_reserve"),
        "assumptions": item.get("assumptions"),
        "source": item.get("source"),
        "reason": item.get("reason"),
    }


def build_scenarios(report, scenario_results):
    rows = (report.get("financial_calculations") or {}).get("periods") or []
    margins = [dec(r.get("margin_after_credit", r.get("margin_after_debt"))) for r in rows]
    reserves = [dec(r.get("projected_reserve", r.get("closing_cash"))) for r in rows]
    known_margins = [v for v in margins if v is not None]
    known_reserves = [v for v in reserves if v is not None]
    normal = {
        "id": "normal",
        "label": "Situation normale",
        "status": "available" if known_margins else "not_available",
        "min_margin": text(min(known_margins)) if known_margins else None,
        "min_reserve": text(min(known_reserves)) if known_reserves else None,
        "assumptions": "Flux fournis sans hypothèse dégradée.",
        "source": "stored_base",
    }
    by_id = {item.get("id"): item for item in scenario_results or []}
    adverse = _scenario_view(by_id.get("adverse"), "adverse", "Situation défavorable")
    severe = _scenario_view(by_id.get("severe"), "severe", "Situation fortement défavorable")
    return {
        "normal": normal,
        "adverse": adverse,
        "severe": severe,
        "notice": "Les scénarios sont des hypothèses explicites, pas des prévisions.",
    }


def build_affordability(report, intelligence, case, request, institution):
    terms = report.get("financing_conditions") or {}
    principal = dec(terms.get("principal"))
    if principal is None:
        principal = dec((case.get("requested_loan") or {}).get("principal", {}).get("value"))
    duration = request.requested_duration_months or terms.get("duration_months") or terms.get("payment_count")
    duration = int(duration) if duration is not None else None
    instalment = dec(terms.get("maximum_instalment"))
    rate = dec(terms.get("annual_nominal_rate"))
    total_cost = dec(terms.get("total_credit_cost"))
    capacity = dec(intelligence["capacity"]["monthly_before_new_debt"])
    min_margin = dec(intelligence["capacity"]["minimum_margin_after_debt"])
    debt_ratio = None
    for criterion in intelligence["criteria"]:
        if criterion["id"] in {"debt_service_ratio", "debt_burden"}:
            debt_ratio = dec(criterion["value"])
            break
    safety = Decimal("0.15")
    max_instalment = (
        None if capacity is None or capacity <= 0 else (capacity * (Decimal(1) - safety)).quantize(CENT)
    )
    theoretical = annuity_principal(max_instalment, rate, duration) if max_instalment is not None else None
    recommended = None
    if theoretical is not None:
        recommended = (theoretical * Decimal("0.80")).quantize(CENT)
        if principal is not None:
            recommended = min(recommended, principal)
    remaining_capacity = None
    if institution and institution.get("remaining_capacity") is not None:
        remaining_capacity = dec(institution["remaining_capacity"])
        if recommended is not None and remaining_capacity is not None:
            recommended = min(recommended, remaining_capacity)
    amount_gap = None
    if principal is not None and recommended is not None:
        amount_gap = (principal - recommended).quantize(CENT)
    return {
        "requested": {
            "principal": text(principal),
            "duration_months": duration,
            "maximum_instalment": text(instalment),
            "annual_nominal_rate": text(rate, 10),
            "total_credit_cost": text(total_cost),
        },
        "capacity": {
            "monthly_before_new_debt": text(capacity),
            "minimum_margin_after_debt": text(min_margin),
            "safety_margin_applied": text(safety, 4),
            "maximum_sustainable_instalment": text(max_instalment),
            "formula": "capacité mensuelle × (1 − marge de sécurité de 15 %)",
        },
        "amounts": {
            "theoretical_max_amount": text(theoretical),
            "recommended_max_amount": text(recommended),
            "requested_amount": text(principal),
            "amount_above_recommended": text(amount_gap),
            "institution_remaining_capacity": text(remaining_capacity),
            "formula": "montant = échéance soutenable × annuité actualisée sur la durée, au taux fourni",
        },
        "post_financing": {
            "debt_ratio": text(debt_ratio),
            "remaining_margin": text(min_margin),
            "requested_instalment_supported": (
                None
                if instalment is None or max_instalment is None
                else instalment <= max_instalment
            ),
        },
        "notice": (
            "Le montant théoriquement supportable n’est pas le montant recommandé. "
            "Le montant recommandé applique une marge de sécurité et les limites de garantie disponibles."
        ),
    }


def build_decision(report, case, intelligence, reliability, scenarios, affordability, request, institution):
    """Produit la recommandation de garantie et ses justifications."""
    favorable = []
    unfavorable = []
    reserves = []
    conditions = []

    score = dec(intelligence["score"]["value"])
    if score is not None and score >= Decimal(65):
        favorable.append("Score financier " + text(score) + "/100 (" + intelligence["score"]["label"] + ").")
    if intelligence["score"]["coverage"] is not None and dec(intelligence["score"]["coverage"]) >= Decimal("0.85"):
        favorable.append("Couverture des critères satisfaisante.")
    if reliability["level"] in {"adequate", "adequate_with_reserves"}:
        favorable.append("Dossier jugé fiable sur les pièces fournies.")

    for risk in intelligence["risks"]:
        if risk["level"] in {"high", "critical"}:
            unfavorable.append(risk["label"] + " — " + risk["explanation"])
        elif risk["level"] == "moderate":
            reserves.append(risk["label"] + " — " + risk["explanation"])

    base_margin = dec(intelligence["capacity"]["minimum_margin_after_debt"])
    base_reserve = None
    for group in intelligence["groups"]:
        for item in group["items"]:
            if item["label"] in {"Réserve minimale projetée", "Trésorerie minimale"}:
                base_reserve = dec(item["value"])
    debt_ratio = None
    for criterion in intelligence["criteria"]:
        if criterion["id"] in {"debt_service_ratio", "debt_burden"}:
            debt_ratio = dec(criterion["value"])
            break
    dscr = None
    for criterion in intelligence["criteria"]:
        if criterion["id"] == "dscr":
            dscr = dec(criterion["value"])
            break

    critical_blockers = []
    if base_margin is not None and base_margin < 0:
        critical_blockers.append("Marge après crédit négative sur au moins une période.")
    if base_reserve is not None and base_reserve < 0:
        critical_blockers.append("Réserve ou trésorerie projetée négative.")
    if dscr is not None and dscr < 1:
        critical_blockers.append("DSCR inférieur à 1 : le service de la dette n’est pas couvert.")
    if debt_ratio is not None and intelligence["core"] == "individuals" and debt_ratio >= Decimal("0.60"):
        critical_blockers.append("Taux d’endettement supérieur ou égal à 60 %.")

    incomplete_blockers = []
    if reliability["suspended"]:
        incomplete_blockers.append("Dossier suspendu : contradictions documentaires à lever.")
    if intelligence["score"]["status"] != "available":
        incomplete_blockers.append("Score financier indisponible : données critiques manquantes.")
    if scenarios["adverse"]["status"] != "available" or scenarios["severe"]["status"] != "available":
        incomplete_blockers.append("Scénarios défavorable et fortement défavorable non disponibles.")

    amount_gap = dec(affordability["amounts"]["amount_above_recommended"])
    if amount_gap is not None and amount_gap > 0:
        conditions.append(
            "Réduire le montant garanti à " + affordability["amounts"]["recommended_max_amount"]
            + " XOF au plus, ou documenter un apport ou une capacité complémentaire."
        )
    if scenarios["adverse"]["status"] == "available" and dec(scenarios["adverse"]["min_margin"]) is not None and dec(scenarios["adverse"]["min_margin"]) < 0:
        conditions.append("Scénario défavorable déficitaire : renforcer la réserve ou réduire l’échéance.")
    if scenarios["severe"]["status"] == "available" and dec(scenarios["severe"]["min_margin"]) is not None and dec(scenarios["severe"]["min_margin"]) < 0:
        reserves.append("Scénario fortement défavorable déficitaire : risque résiduel à accepter explicitement.")
    if debt_ratio is not None and intelligence["core"] == "individuals" and Decimal("0.40") <= debt_ratio < Decimal("0.60"):
        conditions.append("Taux d’endettement élevé : confirmer la stabilité des revenus et l’absence de dettes non déclarées.")
    if dscr is not None and Decimal("1") <= dscr < Decimal("1.20"):
        conditions.append("DSCR proche de 1 : documenter la saisonnalité et les encaissements clients.")
    for item in reliability["human_verifications"][:20]:
        reserves.append("Vérification humaine : " + item)

    guarantee_requested = request.guarantee_amount
    if guarantee_requested is None:
        guarantee_requested = dec(affordability["requested"]["principal"])
    recommended = dec(affordability["amounts"]["recommended_max_amount"])
    recommended_guarantee = None
    if recommended is not None and guarantee_requested is not None:
        recommended_guarantee = min(recommended, guarantee_requested)
    elif recommended is not None:
        recommended_guarantee = recommended
    elif guarantee_requested is not None and not critical_blockers and not incomplete_blockers:
        recommended_guarantee = guarantee_requested

    if critical_blockers:
        outcome = "defavorable"
    elif incomplete_blockers:
        outcome = "analyse_complementaire_necessaire"
    elif conditions or reserves:
        outcome = "favorable_sous_conditions"
    else:
        outcome = "favorable"

    if outcome == "defavorable":
        recommended_guarantee = ZERO
    elif outcome == "analyse_complementaire_necessaire":
        recommended_guarantee = None

    if outcome == "favorable_sous_conditions" and not conditions:
        conditions.append("Maintenir les conditions financières analysées et documenter leur continuité.")

    next_steps = {
        "favorable": [
            "Transmettre la recommandation à la validation humaine habilitée.",
            "Ne pas présenter la garantie comme approuvée avant décision formelle.",
        ],
        "favorable_sous_conditions": [
            "Lever les conditions et réserves listées avant validation.",
            "Soumettre la garantie à la validation humaine habilitée.",
        ],
        "analyse_complementaire_necessaire": [
            "Compléter les informations et justificatifs manquants.",
            "Relancer une analyse décisionnelle sur les données actualisées.",
        ],
        "defavorable": [
            "Ne pas garantir le financement en l’état.",
            "Documenter les motifs et orienter le demandeur vers un plan d’amélioration.",
        ],
    }[outcome]

    return {
        "rules_version": DECISION_RULES_VERSION,
        "outcome": outcome,
        "label": OUTCOME_LABELS[outcome],
        "score": text(score),
        "risk_level": intelligence["score"]["risk_level"],
        "justifications": {
            "favorable": favorable,
            "unfavorable": unfavorable,
            "reserves": reserves,
            "conditions": conditions,
            "blocking": critical_blockers + incomplete_blockers,
        },
        "conditions": conditions,
        "reserves": reserves,
        "next_steps": next_steps,
        "guarantee": {
            "requested_amount": text(guarantee_requested),
            "recommended_amount": text(recommended_guarantee),
            "status": "not_created",
            "human_approval_required": True,
            "human_approval_status": "pending",
            "notice": (
                "Recommandation de garantie ≠ garantie approuvée ≠ crédit accordé par une banque. "
                "La validation humaine reste obligatoire."
            ),
        },
        "institution": institution,
        "notice": (
            "Décision déterministe fondée sur les données et règles stockées. "
            "Aucune probabilité calibrée, aucun modèle entraîné."
        ),
    }
