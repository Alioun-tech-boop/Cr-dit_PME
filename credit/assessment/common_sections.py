from decimal import Decimal

from credit.shared.calculation import total
from credit.assessment.context import ratio


def identity(ctx, business=False):
    s = ctx.section(
        "identity",
        "Identité juridique et qualité documentaire"
        if business
        else "Identité, ménage et qualité documentaire",
        "documentary",
    )
    for path in ["name", "evidence", "analysis_details.identity", "analysis_details.as_of"]:
        ctx.use(s, path)
    checks = ctx.details.identity
    if checks.subject_linked is not True:
        s.missing_information.append("Confirmer le rattachement des pièces au bon demandeur")
    if business:
        if checks.representation_confirmed is not True:
            s.missing_information.append("Vérifier la représentation de l’entreprise")
        if checks.authorizations_applicable is None:
            s.missing_information.append(
                "Préciser les autorisations pertinentes à cette activité, sans obligation inventée"
            )
        elif checks.authorizations_applicable and checks.authorizations_confirmed is not True:
            s.missing_information.append("Vérifier les autorisations déclarées pertinentes")
    else:
        ctx.use(s, "household_scope")
        if not ctx.case.household_scope.strip() or checks.household_confirmed is not True:
            s.missing_information.append(
                "Confirmer le périmètre du ménage et les revenus mobilisables"
            )
    if not ctx.details.as_of:
        s.missing_information.append("Date de référence de l’analyse documentaire")
    if not ctx.case.evidence:
        s.missing_information.append("Références des pièces justificatives")
    for evidence in ctx.case.evidence:
        if evidence.status in {"contradictory", "missing", "unverified_extracted"}:
            s.missing_information.append(f"Verifier la preuve {evidence.id} : {evidence.status}")
        if ctx.details.as_of and evidence.collected_at > ctx.details.as_of:
            s.missing_information.append(f"Confirmer la date de collecte future de {evidence.id}")
    if checks.contradictions:
        s.alerts.extend(n.text for n in checks.contradictions)
        s.missing_information.append(
            "Rapprocher les données contradictoires ; aucune fraude déduite automatiquement"
        )
    ctx.metric(
        s,
        "evidence_count",
        Decimal(len(ctx.case.evidence)),
        "pièces",
        "Nombre de références fournies",
    )
    s.strengths.append("Rattachement explicitement déclaré") if checks.subject_linked else None
    return ctx.finish(
        s,
        "Contrôle d’exploitabilité et de rattachement ; ne mesure ni la solvabilité financière ni l’authenticité des documents.",
    )


def debt(ctx, business=False):
    s = ctx.section(
        "debt",
        "Endettement et structure financière"
        if business
        else "Dettes et comportement de remboursement",
    )
    for path in [
        "existing_loans",
        "analysis_details.repayment_observations",
        "analysis_details.repayment_history_applicable",
    ]:
        ctx.use(s, path)
    principal = total(
        ctx.money(s, f"existing_loans.{i}.principal", loan.principal)
        for i, loan in enumerate(ctx.case.existing_loans)
    )
    ctx.metric(
        s,
        "existing_principal",
        principal,
        "XOF",
        "Somme du capital restant à rembourser des échéanciers existants",
    )
    if ctx.details.repayment_history_applicable is None:
        s.missing_information.append(
            "Préciser si un historique de remboursement existe ; son absence ne prouve pas un bon comportement"
        )
    if ctx.details.repayment_history_applicable and not ctx.details.repayment_observations:
        s.missing_information.append("Historique daté des arriérés, retards et restructurations")
    refs = {loan.reference for loan in ctx.case.existing_loans}
    for i, item in enumerate(ctx.details.repayment_observations):
        if item.loan_reference not in refs:
            s.missing_information.append(
                f"Rattacher l’historique de dette {item.loan_reference} à un échéancier"
            )
        arrears = ctx.money(s, f"repayment_observations.{i}.arrears", item.arrears)
        key = f"arrears_{i}"
        ctx.metric(s, key, arrears, "XOF", "Arriérés déclarés à la date indiquée", item.as_of)
        ctx.fact(
            s,
            "arrears_clear_" + str(i),
            key,
            "eq",
            message=f"Arriérés signalés sur {item.loan_reference} : état actualisé et échéancier documenté nécessaires",
            failure="vigilance",
        )
        if item.days_past_due is None:
            s.missing_information.append(f"Nombre de jours de retard : {item.loan_reference}")
        elif item.days_past_due > 0:
            s.alerts.append(
                f"{item.loan_reference} : {item.days_past_due} jours de retard observés"
            )
        if item.restructuring_count is None:
            s.missing_information.append(f"Historique des restructurations : {item.loan_reference}")
        elif item.restructuring_count:
            s.alerts.append(
                f"{item.loan_reference} : {item.restructuring_count} restructurations à analyser"
            )
    if business:
        for key in ["equity", "off_balance_commitments", "tax_arrears", "social_arrears"]:
            ctx.use(s, "analysis_details." + key)
            value = ctx.money(s, key, getattr(ctx.details, key))
            ctx.metric(s, key, value, "XOF", "Valeur structurée à la date de référence")
            if key.endswith("arrears"):
                ctx.fact(
                    s,
                    key + "_clear",
                    key,
                    "eq",
                    failure="vigilance",
                    message="Arriérés fiscaux ou sociaux à actualiser",
                )
        equity = next(m.value for m in s.indicators if m.id == "equity")
        ctx.metric(
            s,
            "debt_equity",
            ratio(principal, equity),
            "ratio",
            "Capital existant / fonds propres, seulement si fonds propres > 0",
        )
        if equity is not None and equity <= 0:
            s.alerts.append(
                "Fonds propres nuls ou négatifs : ratio dette/fonds propres indisponible, aucune valeur négative favorable."
            )
            s.status = "defavorable"
    else:
        for i, p in enumerate(ctx.case.periods):
            ctx.use(s, f"periods.{i}.payroll_loan_treatment")
            ctx.use(s, f"periods.{i}.payroll_loan_deductions")
            if p.payroll_loan_treatment == "unclear":
                s.missing_information.append(
                    f"Ventiler les retenues de prêts du salaire en {p.period}"
                )
        if not ctx.case.existing_loans and ctx.details.repayment_history_applicable is False:
            s.strengths.append(
                "Aucune dette existante déclarée ; aucun historique de bon payeur inféré."
            )
    return ctx.finish(
        s,
        "Les échéanciers comprennent capital, intérêts et frais. Les retenues salariales sont réintégrées au revenu si elles ont déjà été déduites, puis les échéances sont retranchées une seule fois.",
    )


def capacity(ctx, business=False):
    s = ctx.section("capacity", "Capacité de remboursement")
    for path in ["periods", "existing_loans", "requested_loan"]:
        ctx.use(s, path)
    ratios = []
    for row in ctx.financial.periods:
        margin = row.margin_after_debt
        key = "margin_" + row.period.isoformat()
        available = row.cash_available_for_debt if business else row.available_before_debt
        ctx.metric(
            s,
            "available_" + str(row.period),
            available,
            "XOF",
            "Encaissements − sorties nécessaires hors dette"
            if business
            else "Revenus nets retenus − dépenses essentielles",
            row.period,
        )
        ctx.metric(
            s,
            key,
            margin,
            "XOF",
            "Disponible avant dette − service dette existante − service nouvelle dette",
            row.period,
        )
        ctx.fact(
            s,
            "nonnegative_" + str(row.period),
            key,
            "ge",
            message=f"Marge de remboursement déficitaire en {row.period} ; revue obligatoire.",
        )
        coverage = row.debt_service_coverage if business else row.debt_to_income
        ctx.metric(
            s,
            ("coverage_" if business else "debt_weight_") + str(row.period),
            coverage,
            "ratio",
            "Disponible pour dette / service total, si service > 0"
            if business
            else "Service total / revenus retenus, si revenus > 0",
            row.period,
        )
        r = coverage if business else ratio(margin, row.net_retained_income)
        if r is not None:
            ratios.append(r)
        if margin is None:
            s.missing_information.append(
                "Flux et services de dette à compléter en " + str(row.period)
            )
    key = "minimum_coverage" if business else "minimum_margin_income"
    ctx.metric(
        s,
        key,
        min(ratios) if ratios else None,
        "ratio",
        "Minimum des ratios par période calculables ; les périodes sans dette sont exclues de la couverture",
    )
    if not ratios:
        s.missing_information.append("Dénominateur positif nécessaire au ratio de capacité")
    s.missing_information.extend(ctx.financial.information_requested)
    if not s.alerts and not s.missing_information:
        s.strengths.append("Aucune marge périodique négative dans les flux fournis.")
    return ctx.finish(
        s,
        "Chaque période est examinée. Un total annuel favorable ne masque pas un déficit mensuel. Les projections sont des hypothèses, pas des recettes certaines.",
    )


def financing(ctx, policy=None, business=False):
    s = ctx.section(
        "project" if business else "financing",
        "Projet financé et résistance aux chocs" if business else "Cohérence du financement",
    )
    ctx.use(s, "analysis_details.funding")
    ctx.use(s, "requested_loan")
    plan = ctx.details.funding
    need = ctx.money(s, "funding.justified_need", plan.justified_need)
    announced = ctx.money(s, "funding.announced_contribution", plan.announced_contribution)
    verified = ctx.money(s, "funding.verified_contribution", plan.verified_contribution)
    principal = ctx.money(s, "requested_loan.principal", ctx.case.requested_loan.principal)
    required = None if need is None or principal is None else max(Decimal(0), need - principal)
    if policy and need is not None:
        required = max(required or Decimal(0), need * policy.product.minimum_contribution_share)
    gap = None if required is None or verified is None else max(Decimal(0), required - verified)
    ctx.metric(
        s,
        "contribution_gap",
        gap,
        "XOF",
        "max(0, apport nécessaire − apport vérifié) ; aucun apport supposé disponible",
    )
    ctx.metric(
        s,
        "announced_contribution",
        announced,
        "XOF",
        "Apport annoncé séparément de l’apport vérifié",
    )
    ctx.metric(
        s,
        "required_contribution",
        required,
        "XOF",
        "max(besoin − crédit, minimum du produit lorsqu’une politique applicable le définit)",
    )
    if gap and gap > 0:
        s.alerts.append(
            "Apport justifié insuffisant : écart à couvrir par des ressources réellement vérifiées."
        )
    if need is not None and principal is not None and principal > need:
        s.alerts.append("Montant demandé supérieur au besoin justifié.")
    schedule = ctx.case.requested_loan.schedule
    cost = total(
        ctx.money(
            s, f"requested_loan.schedule.{i}.{key}", getattr(p, key), optional=key != "principal"
        )
        for i, p in enumerate(schedule)
        for key in ["principal", "interest", "fees"]
    )
    ctx.metric(
        s,
        "total_repayment",
        cost,
        "XOF",
        "Somme du capital, des intérêts et frais exigibles sur l’échéancier complet",
    )
    ctx.metric(
        s,
        "total_credit_cost",
        None if cost is None or principal is None else cost - principal,
        "XOF",
        "Total à rembourser − capital demandé",
    )
    ctx.metric(
        s,
        "instalment_count",
        Decimal(len(schedule)),
        "échéances",
        "Nombre d’échéances explicites ; ne suppose pas une durée mensuelle pour un crédit irrégulier",
    )
    if not plan.purpose:
        s.missing_information.append("Objet du crédit et justificatif du besoin")
    if business:
        ctx.use(s, "analysis_details.project_receipts")
        if plan.implementation_start is None or plan.expected_start is None:
            s.missing_information.append("Dates de mise en œuvre et de démarrage attendues")
        for p in ctx.details.project_receipts:
            if not p.included_in_receipts:
                s.alerts.append(
                    f"Recette de projet {p.period} non incluse dans le scénario de base, pas d’ajout automatique."
                )
        s.alerts.append(
            "Les recettes de projet sont prévisionnelles et nécessitent des hypothèses justifiées."
        )
    if s.alerts and s.status == "favorable":
        s.status = "vigilance"
    return ctx.finish(
        s,
        "Besoin, apport et coûts sont présentés séparément. Aucun emprunt artificiel d’apport ni baisse des dépenses essentielles n’est proposé.",
    )
