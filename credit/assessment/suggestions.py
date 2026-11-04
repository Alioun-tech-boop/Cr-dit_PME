from credit.assessment.contracts import Suggestion
from credit.assessment.simulation import SimulationSpec, prepare_simulation
from credit.assessment.reporting import compare_financial
from credit.shared.schedule import rounded


def suggest(ctx, sections, policy, calculate):
    result = []
    by_id = {s.id: s for s in sections}
    for section in sections:
        if section.missing_information:
            result.append(
                Suggestion(
                    id="complete_" + section.id,
                    section_id=section.id,
                    problem="Données ou validations manquantes",
                    triggers=section.missing_information,
                    action="Compléter : " + " ; ".join(section.missing_information),
                    recipient="analyste",
                    priority="haute",
                    prerequisites=[
                        "Rattacher les pièces au dossier et à leur période ; revue humaine des transcriptions OCR"
                    ],
                    costs_and_limits=[
                        "La collecte améliore l’exploitabilité, pas une probabilité de remboursement mesurée."
                    ],
                    evidence_needed=section.missing_information,
                )
            )
    if any(
        p.payroll_loan_treatment == "unclear"
        for p in getattr(ctx.case, "periods", [])
        if hasattr(p, "payroll_loan_treatment")
    ):
        result.append(
            Suggestion(
                id="clarify_payroll",
                section_id="debt",
                problem="Retenues de prêts ambiguës",
                triggers=["payroll_loan_treatment=unclear"],
                action="Demander la ventilation du net avant/après retenues et rapprocher chaque prêt à son échéancier.",
                recipient="analyste",
                priority="haute",
                prerequisites=["Bulletin et état de dette de la même période"],
                costs_and_limits=["Aucun montant inconnu remplacé par zéro."],
                evidence_needed=[
                    "Bulletin de salaire",
                    "Ventilation des retenues",
                    "Échéanciers existants",
                ],
            )
        )
    arrears = [
        p
        for p in ctx.details.repayment_observations
        if p.arrears.value is not None and p.arrears.value > 0
    ]
    if arrears:
        result.append(
            Suggestion(
                id="arrears_schedule",
                section_id="debt",
                problem="Arriérés documentés à actualiser",
                triggers=[f"arrears:{p.loan_reference}" for p in arrears],
                action="Demander un état actualisé et tester uniquement un échéancier de restructuration documenté.",
                recipient="preteur",
                priority="haute",
                prerequisites=["Accord du prêteur et calendrier explicite"],
                costs_and_limits=[
                    "Une restructuration ne supprime pas une dette ni les frais ; pas de remise supposée."
                ],
                evidence_needed=["État des arriérés", "Proposition d’échéancier datée"],
            )
        )
    activity = by_id.get("activity")
    if activity:
        concentration = next(
            (m.value for m in activity.indicators if m.id == "largest_customer_share"), None
        )
        if concentration is not None and (
            concentration == 1
            or any(
                r.id == "criterion:customer_dependency" and r.passed is False
                for r in activity.rules
            )
        ):
            result.append(
                Suggestion(
                    id="customer_followup",
                    section_id="activity",
                    problem="Concentration des encaissements clients",
                    triggers=["largest_customer_share=" + str(concentration)],
                    action="Vérifier contrats, échéances clients et suivre les encaissements concentrés ; simuler un retard client explicitement daté.",
                    recipient="analyste",
                    priority="moyenne",
                    prerequisites=[
                        "Ventilation clients rapprochée",
                        "Montant et période du retard",
                    ],
                    costs_and_limits=[
                        "Diversifier les clients peut coûter du temps et des moyens ; aucun effet causal sur une PD n’est affirmé."
                    ],
                    evidence_needed=[
                        "Contrats clients",
                        "Balance âgée",
                        "Historique des encaissements",
                    ],
                )
            )
    funding = by_id.get("project", by_id.get("financing"))
    gap = next((m.value for m in funding.indicators if m.id == "contribution_gap"), None)
    if gap is not None and gap > 0:
        result.append(
            Suggestion(
                id="contribution_gap",
                section_id=funding.id,
                problem="Apport vérifié insuffisant",
                triggers=["contribution_gap=" + str(gap)],
                action=f"Justifier {gap} XOF de ressources propres disponibles ou revoir le projet.",
                recipient="demandeur",
                priority="haute",
                prerequisites=["Disponibilité réelle des fonds"],
                simulated_effect={
                    "additional_verified_contribution_needed": gap,
                    "currency": "XOF",
                    "availability_assumed": False,
                },
                costs_and_limits=[
                    "Ne pas emprunter artificiellement l’apport ; son existence n’est pas présumée."
                ],
                evidence_needed=["Preuve d’apport mobilisable", "Budget justifié"],
            )
        )
    deficit = bool(ctx.financial.financial_findings.deficit_periods)
    need = ctx.details.funding.justified_need
    principal = ctx.case.requested_loan.principal.value
    excessive = (
        need is not None
        and need.value is not None
        and principal is not None
        and principal > need.value
    )
    if deficit or excessive:
        for kind in ["lower_amount", "extend_term"]:
            prerequisites = [
                "Conditions et limites du produit applicables",
                "Hypothèses explicites des périodes nécessaires",
            ]
            spec = None
            if (
                policy
                and principal is not None
                and ctx.case.requested_loan.amortization_method == "monthly_constant"
            ):
                if kind == "lower_amount":
                    spec = SimulationSpec(
                        kind=kind, principal=rounded(principal * policy.product.lower_amount_factor)
                    )
                elif len(ctx.case.requested_loan.schedule) < policy.product.max_months:
                    spec = SimulationSpec(
                        kind=kind,
                        months=min(
                            policy.product.max_months, len(ctx.case.requested_loan.schedule) * 2
                        ),
                    )
            effect = None
            if spec:
                try:
                    prepared = prepare_simulation(ctx.case, spec, policy)
                    effect = {
                        "status": prepared["status"],
                        "terms": prepared["terms"],
                        "parameters": spec.model_dump(mode="json"),
                        "missing_information": prepared["missing_information"],
                    }
                    if prepared["case"] is not None:
                        after = calculate(prepared["case"])
                        effect["financial_comparison"] = compare_financial(ctx.financial, after)
                except ValueError as error:
                    effect = {"status": "not_available", "reason": str(error)}
            result.append(
                Suggestion(
                    id=kind,
                    section_id="capacity",
                    problem="Montant ou échéancier en tension avec le budget",
                    triggers=["period_deficit" if deficit else "requested_amount_above_need"],
                    action="Tester un crédit de montant inférieur."
                    if kind == "lower_amount"
                    else "Tester un allongement autorisé, en comparant la nouvelle échéance ET le coût total.",
                    recipient="preteur",
                    priority="haute",
                    prerequisites=prerequisites,
                    simulated_effect=effect,
                    costs_and_limits=[
                        "Simulation conditionnelle, pas une offre ou un accord.",
                        "Un allongement peut accroître intérêts et frais ; une réduction peut laisser un besoin non financé.",
                        "Dépenses essentielles et dettes conservées ; aucune PD causale déduite du changement de ratio.",
                    ],
                    evidence_needed=[
                        "Conditions du produit",
                        "Échéancier",
                        "Budget complet sur la nouvelle durée",
                        "Apport éventuel réellement vérifié",
                    ],
                )
            )
    for item in result:
        if item.section_id in by_id:
            by_id[item.section_id].suggestion_ids.append(item.id)
    return result
