"""Orchestration déterministe v2. Aucune importation du scoring dual ni d'un modèle."""

from decimal import Decimal, localcontext, ROUND_HALF_UP

from credit.assessment.context import AnalysisContext
from credit.assessment.contracts import Suggestion
from credit.assessment.reporting import financial_risk, compare_financial
from credit.assessment.simulation import loan_summary
from credit.assessment.suggestions import suggest
from credit.assessment.timing import analyze_timing
from credit.businesses import sections as bs
from credit.businesses.engine import analyze as business_calculate
from credit.individuals import sections as ins
from credit.individuals.engine import analyze as individual_calculate
from credit.shared.arithmetic import arithmetic_context
from credit.shared.normalization import effective_case
from credit.financial_v2 import ENGINE_VERSION
from credit.financial_v2.contracts import Facts, Report, Stress
from credit.financial_v2.diagnostics import (
    statistics,
    reconcile,
    add_history_section,
    additional_business,
    recurrent_share,
)
from credit.financial_v2.financing import variants, constraints, min_or_none, loan_constraints
from credit.financial_v2.policy import authorize, qualify
from credit.financial_v2.scenarios import prepare, search


def financial_payload(result):
    payload = result.model_dump(mode="json")
    payload.pop("scoring", None)
    return payload


class BaseAnalysisEngine:
    def calculate(self, case):
        effective, _ = effective_case(case)
        result = self.calculator(effective)
        unspecified_existing = any(
            not loan.schedule
            and loan.principal.state in {"unknown", "estimated"}
            and loan.principal.value is None
            for loan in effective.existing_loans
        )
        unspecified_new = (
            not effective.requested_loan.schedule
            and effective.requested_loan.principal.value is None
        )
        if unspecified_existing or unspecified_new:
            result.status = "incomplete"
            result.information_requested.append(
                "Échéancier et capital des dettes inconnues à fournir ; absence d’échéancier différente d’une dette nulle."
            )
            result.financial_findings.minimum_balance = None
            result.financial_findings.minimum_balance_date = None
            for row in result.periods:
                if unspecified_existing:
                    row.existing_debt_service = None
                if unspecified_new:
                    row.new_debt_service = None
                if hasattr(row, "margin_after_credit"):
                    row.margin_after_credit = None
                    row.projected_reserve = None
                    row.debt_to_income = None
                else:
                    row.margin_after_debt = None
                    row.closing_cash = None
                    row.debt_service_coverage = None
        return result

    def analyze(
        self,
        case,
        policy=None,
        mode="real",
        facts=None,
        scenarios=None,
        reverse_tests=None,
        candidates=None,
        institution_id=None,
    ):
        with localcontext(arithmetic_context()) as context:
            context.prec = 28
            context.rounding = ROUND_HALF_UP
            return self._analyze(
                case,
                policy,
                mode,
                facts or Facts(),
                scenarios or [],
                reverse_tests or [],
                candidates or [],
                institution_id,
            )

    def _analyze(
        self, case, policy, mode, facts, scenarios, reverse_tests, candidates, institution_id
    ):
        if mode not in {"real", "demonstration"}:
            raise ValueError("Mode inconnu")
        authorize(policy, case, self.core, mode, institution_id)
        if len({s.id for s in scenarios}) != len(scenarios):
            raise ValueError("Identifiants de scénarios dupliqués")
        effective, normalization = effective_case(case)
        reconciliation = reconcile(effective, facts)
        financial = self.calculate(effective)
        ctx = AnalysisContext(effective, financial)
        sections = self.sections(ctx)
        if self.core == "individuals":
            reserve = ctx.sections["reserve"]
            reserve.title = "Épargne et réserve mobilisable"
            reserve.missing_information = [
                m
                for m in reserve.missing_information
                if m
                != "Scénarios explicites de baisse de revenu, hausse de charges ou retard à fournir"
            ]
            if reserve.status == "incomplet" and not reserve.missing_information:
                reserve.status = "vigilance" if reserve.alerts else "favorable"
        stats = statistics(
            case,
            policy.minimum_history_periods if policy else 3,
            policy.seasonality_minimum_months if policy else 24,
        )
        financial.financial_findings.income_variability_cv = (
            stats["coefficient_of_variation"] if self.core == "individuals" else None
        )
        sections.append(add_history_section(ctx, stats))
        for section in sections:
            for indicator in section.indicators:
                if indicator.id == "history_cv":
                    indicator.value = stats["coefficient_of_variation"]
                    indicator.unavailable_reason = (
                        None
                        if indicator.value is not None
                        else "Historique comparable suffisant requis selon paramètres v2"
                    )
        if scenarios:
            for section in sections:
                if section.id == "project":
                    section.missing_information = [
                        x
                        for x in section.missing_information
                        if x != "Scénarios de ventes, coûts, retard client ou démarrage à préciser"
                    ]
        if self.core == "businesses" and facts.supplier_flows_complete:
            activity = ctx.sections["activity"]
            payments = [
                p
                for p in case.analysis_details.counterparties
                if p.role == "supplier" and p.flow_kind == "payment"
            ]
            totals = {}
            known = bool(payments)
            for payment in payments:
                value = ctx.money(activity, "supplier." + payment.name, payment.amount)
                if value is None:
                    known = False
                else:
                    totals[payment.name] = totals.get(payment.name, Decimal(0)) + value
            denominator = sum(totals.values(), Decimal(0))
            ctx.metric(
                activity,
                "supplier_concentration",
                max(totals.values()) / denominator if known and denominator > 0 else None,
                "ratio",
                "Paiements du premier fournisseur / paiements fournisseurs exhaustifs fournis sur les mêmes périodes",
                paths=["analysis_details.counterparties", "facts.supplier_flows_complete"],
            )
        if self.core == "businesses":
            sections.append(additional_business(ctx, facts))
            if facts.tax_basis == "unknown":
                for section in sections:
                    for indicator in section.indicators:
                        if indicator.id in {"dso", "dpo", "dio"}:
                            indicator.value = None
                            indicator.unavailable_reason = (
                                "Traitement des taxes des soldes et dénominateurs à confirmer"
                            )
                            section.missing_information.append(indicator.unavailable_reason)
                            if section.status == "favorable":
                                section.status = "incomplet"
        stress_results = []
        comparisons = []
        for scenario in scenarios:
            item = {"scenario": scenario.model_dump(mode="json")}
            try:
                alternative, notes, sensitivity = prepare(effective, scenario, facts)
                result = self.calculate(alternative)
                comparison = compare_financial(financial, result)
                item.update(
                    status="available",
                    input_snapshot=alternative.model_dump(mode="json"),
                    financial_calculations=financial_payload(result),
                    comparison=comparison,
                    assumptions=notes,
                    costs_sensitivity=sensitivity,
                    reserve_exhaustion_date=next(
                        (
                            p.period.isoformat()
                            for p in result.periods
                            if p.closing_reserve_or_cash is not None
                            and p.closing_reserve_or_cash <= 0
                        ),
                        None,
                    ),
                )
                comparisons.append(
                    {
                        "kind": "stress",
                        "assumptions": scenario.model_dump(mode="json"),
                        **comparison,
                    }
                )
            except ValueError as exc:
                item.update(status="needs_explicit_data", information_requested=[str(exc)])
            stress_results.append(item)
        resistance = ctx.section("resistance", "Résistance aux difficultés")
        for item in stress_results:
            if item["status"] != "available":
                resistance.missing_information.extend(item["information_requested"])
            else:
                rows = item["financial_calculations"]["periods"]
                margins = [
                    Decimal(p.get("margin_after_credit", p.get("margin_after_debt")))
                    for p in rows
                    if p.get("margin_after_credit", p.get("margin_after_debt")) is not None
                ]
                ctx.metric(
                    resistance,
                    "stress_min_margin_" + item["scenario"]["id"],
                    min(margins) if len(margins) == len(rows) and margins else None,
                    "XOF",
                    "Minimum des marges recalculées sur la copie du dossier",
                    paths=["periods", "scenarios." + item["scenario"]["id"]],
                )
                if margins and min(margins) < 0:
                    resistance.status = "defavorable"
                    resistance.alerts.append(
                        item["scenario"]["name"] + " : marge déficitaire sous ces hypothèses."
                    )
        if not scenarios:
            resistance.missing_information.append(
                "Scénarios explicites non fournis ; résistance non évaluée."
            )
        sections.append(
            ctx.finish(
                resistance, "Résultats conditionnels, sans estimation de probabilité de défaut."
            )
        )
        timing = analyze_timing(ctx)
        risk = financial_risk(financial, timing)
        if reconciliation["monthly_gaps"] and risk["status"] != "payment_pressure":
            risk["status"] = "incomplete"
        risk["horizon_notice"] = (
            "Toute la durée inscrite dans l’échéancier fourni est couverte ; aucune extrapolation après les périodes saisies."
        )
        missing = sorted(
            set(
                [m for s in sections for m in s.missing_information]
                + financial.information_requested
                + timing["information_requested"]
                + reconciliation["information_requested"]
            )
        )
        if (
            any(p.basis == "forecast" for p in case.periods)
            and not case.analysis_details.projection_assumptions
        ):
            missing.append("Hypothèses explicites des projections à justifier")
        if reconciliation["monthly_gaps"]:
            missing.append("Périodes mensuelles manquantes dans la projection")
        review = bool(
            risk["period_deficits"]
            or risk["negative_balance_periods"]
            or (timing["minimum_balance"] is not None and timing["minimum_balance"] < 0)
            or any(c["status"] != "matched" for c in reconciliation["checks"])
            or any(
                "comptée plusieurs fois" in w or "chevauchantes" in w
                for w in reconciliation["warnings"]
            )
        )
        metrics = {i.id: i.value for s in sections for i in s.indicators}
        metrics.update(
            minimum_margin=min_or_none([p.margin_after_debt for p in financial.periods]),
            minimum_reserve=min_or_none([p.closing_reserve_or_cash for p in financial.periods]),
        )
        ratios = []
        for p in financial.periods:
            total = (
                None
                if p.existing_debt_service is None or p.new_debt_service is None
                else p.existing_debt_service + p.new_debt_service
            )
            numerator = getattr(
                p, "cash_available_for_debt", getattr(p, "available_before_debt", None)
            )
            if total == 0:
                continue
            ratios.append(
                None if numerator is None or total is None or total < 0 else numerator / total
            )
        metrics["minimum_debt_coverage"] = min_or_none(ratios)
        scoring = qualify(metrics, policy, missing, review)
        product_checks = (
            (constraints(financial, policy.product) + loan_constraints(case, policy.product))
            if policy
            else []
        )
        if any(c["passed"] is None for c in product_checks):
            missing.append(
                "Contraintes produit non évaluables : "
                + ", ".join(c["id"] for c in product_checks if c["passed"] is None)
            )
            scoring.update(
                criteria_score=None,
                solvency_score=None,
                risk_index=None,
                criteria_status="incomplete",
                qualification="incomplet",
            )
        if any(c["passed"] is False for c in product_checks):
            scoring["mandatory_review"] = True
            scoring["qualification"] = "defavorable"
            scoring["product_limit_alert"] = (
                "Une limite produit n’est pas respectée, indépendamment du score par critères."
            )
        required = set(policy.required_scenarios if policy else [])
        if required - {s.id for s in scenarios}:
            scoring.update(
                criteria_score=None,
                solvency_score=None,
                risk_index=None,
                criteria_status="incomplete",
                qualification="incomplet",
            )
            missing.append(
                "Scénarios exigés par la politique : "
                + ", ".join(sorted(required - {s.id for s in scenarios}))
            )
            scoring["mandatory_review"] = True
        for item in stress_results:
            if item["scenario"]["id"] in required:
                if item["status"] != "available":
                    scoring["mandatory_review"] = True
                else:
                    from credit.shared.results import AnalysisResult

                    checks = constraints(
                        AnalysisResult.model_validate(item["financial_calculations"]),
                        policy.product,
                    )
                    if any(c["passed"] is not True for c in checks):
                        scoring["mandatory_review"] = True
        reverse = [self.reverse(effective, financial, facts, t, policy) for t in reverse_tests]
        alternatives = variants(effective, policy, candidates, scenarios, facts, self.calculate)
        suggestions = suggest(ctx, sections, None, self.calculate)
        for i, variant in enumerate(alternatives["variants"]):
            suggestions.append(
                Suggestion(
                    id="financing_variant_" + str(i),
                    section_id="financing" if self.core == "individuals" else "project",
                    problem="Comparer un financement alternatif aux contraintes documentées",
                    triggers=["deep_analysis.financing_variants.variants." + str(i)],
                    action="Examiner la variante testée, sans modifier les faits du dossier ni masquer une dette.",
                    recipient="analyste",
                    priority="moyenne" if variant["compatible"] else "haute",
                    prerequisites=[
                        "Produit applicable, projections complètes, taux et frais fournis, apport réellement disponible"
                    ],
                    simulated_effect={
                        "status": variant["status"],
                        "before": variant.get("before"),
                        "after": variant.get("after"),
                        "terms_before": variant.get("terms_before"),
                        "terms_after": variant.get("terms_after"),
                        "constraints": variant["constraints"],
                    },
                    costs_and_limits=[
                        "Comparer échéances et coût total ; une durée supérieure peut augmenter les intérêts.",
                        "Le maximum compatible parmi les candidats testés n’est pas le financement conseillé.",
                    ],
                    evidence_needed=variant.get("information_requested", [])
                    + ["Confirmer les conditions et la disponibilité des ressources"],
                )
            )
        states = []
        if scoring["mandatory_review"]:
            states.append("revue_approfondie_requise")
        if missing:
            states.append("dossier_a_completer")
        if alternatives["status"] == "compatible_alternatives_found":
            states.append("simulation_alternative_disponible")
        states.append("analyse_disponible")
        assumptions = (
            normalization
            + [
                "Montants XOF au centième, ROUND_HALF_UP ; précision Decimal 28 ; ratios techniques à 8 décimales.",
                "Aucune moyenne historique prolongée ; seules les projections fournies sont utilisées.",
                "Granularité mensuelle : des tensions intramensuelles peuvent rester invisibles sans dates détaillées.",
                "Calculs déterministes exclusivement ; aucune PD ou perte attendue calculée.",
                "Garanties complémentaires : elles ne compensent pas un déficit de remboursement.",
            ]
            + [n.text for n in case.analysis_details.projection_assumptions]
        )
        summary = (
            "Analyse financière déterministe des flux fournis. "
            + (
                "Des déficits ou limites imposent une revue approfondie. "
                if scoring["mandatory_review"]
                else "Aucun déficit identifié dans les seuls flux de base recensés. "
            )
            + ("Dossier à compléter. " if missing else "")
            + (
                "Qualification selon politique "
                + policy.id
                + " ("
                + policy.validation_status
                + "). "
                if policy
                else "Aucune politique approuvée fournie : score indisponible. "
            )
            + "Ce rapport ne constitue pas un accord de crédit."
        )
        return Report(
            engine_version=ENGINE_VERSION,
            core=self.core,
            operating_state=states[0],
            operating_states=states,
            summary=summary,
            sections=sections,
            major_alerts=[a for s in sections for a in s.alerts],
            missing_information=sorted(set(missing)),
            financial_risk=risk,
            documentary_quality={
                **financial.documentary_quality,
                "status": sections[0].status,
                "authenticity_status": "not_assessed",
                "coverage": reconciliation["coverage"],
            },
            scoring=scoring,
            suggestions=suggestions,
            comparisons=comparisons,
            financing_conditions=loan_summary(case.requested_loan, ctx.reader),
            financial_calculations=financial_payload(financial),
            assumptions=assumptions,
            sources=[e.model_dump(mode="json") for e in case.evidence],
            versions={
                "engine": ENGINE_VERSION,
                "rules": "financial-facts-v2",
                "mode": mode,
                "policy": policy.id + ":" + policy.version if policy else None,
                "combination": "disabled",
            },
            policy_snapshot=policy.model_dump(mode="json") if policy else None,
            human_validations=[e.model_dump(mode="json") for e in case.evidence if e.review_id],
            deep_analysis={
                "history": stats,
                "reconciliation": reconciliation,
                "income_classification": recurrent_share(case, facts),
                "scenarios": stress_results,
                "reverse_tests": reverse,
                "financing_variants": alternatives,
                "product_constraints": product_checks,
                "facts": facts.model_dump(mode="json"),
                "base_projection": {
                    "method": "provided_periods_only",
                    "frequency": "monthly",
                    "start": case.periods[0].period.isoformat(),
                    "end": case.periods[-1].period.isoformat(),
                    "reserve_exhaustion_date": next(
                        (
                            p.period.isoformat()
                            for p in financial.periods
                            if p.closing_reserve_or_cash is not None
                            and p.closing_reserve_or_cash <= 0
                        ),
                        None,
                    ),
                    "input_paths": ["periods", "existing_loans", "requested_loan"],
                    "assumptions": [n.text for n in case.analysis_details.projection_assumptions],
                    "notice": "Aucune moyenne historique prolongée ; les tensions intramensuelles nécessitent des dates détaillées.",
                },
                "pipeline": [
                    "validation",
                    "normalisation",
                    "rapprochement",
                    "reconstitution",
                    "indicateurs",
                    "historique",
                    "projection_explicitement_fournie",
                    "scenarios",
                    "regles",
                    "sous_analyses",
                    "variantes",
                    "rapport",
                ],
            },
        )

    def reverse(self, case, financial, facts, test, policy):
        def evaluate(x):
            try:
                if test.parameter == "additional_instalment":
                    floor = (
                        policy.product.minimum_margin
                        if policy and policy.product.minimum_margin is not None
                        else Decimal(0)
                    )
                    values = [
                        None if p.margin_after_debt is None else p.margin_after_debt - x - floor
                        for p in financial.periods
                    ]
                else:
                    kwargs = (
                        {test.parameter: x}
                        if test.parameter in {"revenue_drop", "expense_increase"}
                        else {
                            "delay_from": test.delay_from,
                            "delay_to": self.delay_target(case, test.delay_from, int(x)),
                            "delay_amount": test.delay_amount,
                        }
                    )
                    if test.parameter == "delay_periods" and x == 0:
                        result = financial
                    else:
                        stress = Stress(
                            id="reverse",
                            name="Recherche inverse",
                            rationale="Intervalle explicitement fourni",
                            **kwargs,
                        )
                        changed, _, _ = prepare(case, stress, facts)
                        result = self.calculate(changed)
                    values = (
                        [p.closing_reserve_or_cash for p in result.periods]
                        if test.parameter == "delay_periods"
                        else [p.margin_after_debt for p in result.periods]
                    )
                if test.parameter == "additional_instalment":
                    reserve_floor = (
                        policy.product.minimum_reserve
                        if policy and policy.product.minimum_reserve is not None
                        else Decimal(0)
                    )
                    values += [
                        None
                        if p.closing_reserve_or_cash is None
                        else p.closing_reserve_or_cash - x * (i + 1) - reserve_floor
                        for i, p in enumerate(financial.periods)
                    ]
                    if policy and policy.product.minimum_debt_coverage is not None:
                        for p in financial.periods:
                            available = getattr(
                                p,
                                "cash_available_for_debt",
                                getattr(p, "available_before_debt", None),
                            )
                            total = (
                                None
                                if p.existing_debt_service is None or p.new_debt_service is None
                                else p.existing_debt_service + p.new_debt_service
                            )
                            values.append(
                                None
                                if available is None or total is None
                                else available - policy.product.minimum_debt_coverage * (total + x)
                            )
                return min_or_none(values)
            except ValueError:
                return None

        result = search(
            evaluate,
            test.lower,
            test.upper,
            test.steps,
            test.tolerance,
            test.parameter == "delay_periods",
        )
        result.update(
            parameters=test.model_dump(mode="json"),
            notice="Seuil dans cet intervalle et sous ces hypothèses seulement ; aucune probabilité de défaut.",
        )
        if test.parameter == "revenue_drop":
            rows = []
            for p in financial.periods:
                income = getattr(p, "net_retained_income", getattr(p, "operating_receipts", None))
                if income is not None and income > 0 and p.margin_after_debt is not None:
                    rows.append(
                        {
                            "period": p.period.isoformat(),
                            "income_annulling_margin": income - p.margin_after_debt,
                            "drop_annulling_margin": p.margin_after_debt / income,
                            "formula": "(revenu retenu − charges nécessaires − service dette) / revenu retenu",
                        }
                    )
            result["analytical_cross_checks"] = rows
        return result

    @staticmethod
    def delay_target(case, start, offset):
        dates = [p.period for p in case.periods]
        if start not in dates or dates.index(start) + offset >= len(dates):
            raise ValueError("Retard hors horizon explicite")
        return dates[dates.index(start) + offset]


class IndividualAnalysisEngine(BaseAnalysisEngine):
    core = "individuals"
    calculator = staticmethod(individual_calculate)

    def sections(self, ctx):
        return [
            ins.identity(ctx),
            ins.income(ctx),
            ins.budget(ctx),
            ins.debt(ctx),
            ins.capacity(ctx),
            ins.reserve(ctx, []),
            ins.financing(ctx, None),
        ]


class BusinessAnalysisEngine(BaseAnalysisEngine):
    core = "businesses"
    calculator = staticmethod(business_calculate)

    def sections(self, ctx):
        return [
            bs.identity(ctx, business=True),
            bs.activity(ctx),
            bs.profitability(ctx),
            bs.working_capital(ctx),
            bs.treasury(ctx),
            bs.debt(ctx, business=True),
            bs.capacity(ctx, business=True),
            bs.project(ctx, None, []),
            bs.collateral(ctx),
        ]
