from decimal import localcontext, ROUND_HALF_UP
from credit.shared.arithmetic import arithmetic_context

from credit.assessment.context import AnalysisContext, effective_case
from credit.config import ENGINE_VERSION as FINANCIAL_ENGINE_VERSION
from credit.assessment.contracts import AssessmentReport
from credit.assessment.policy import authorize_policy
from credit.assessment.scoring import score_report
from credit.assessment.reporting import financial_risk, summary, compare_financial
from credit.assessment.suggestions import suggest
from credit.assessment.simulation import loan_summary
from credit.assessment.timing import analyze_timing
from credit.individuals import sections as individual_sections
from credit.businesses import sections as business_sections
from credit.individuals.engine import analyze as individual_calculate
from credit.businesses.engine import analyze as business_calculate

ENGINE_VERSION = "section-analysis-1.1.0"


class BaseAnalysisEngine:
    def calculate(self, case, scenario=None):
        effective, _ = effective_case(case)
        return self.calculator(effective, scenario)

    def analyze(
        self,
        case,
        policy=None,
        mode="real",
        stress_scenarios=None,
        model=None,
        scenario=None,
        include_suggestions=True,
    ):
        with localcontext(arithmetic_context()) as context:
            context.prec = 28
            context.rounding = ROUND_HALF_UP
            return self._analyze(
                case, policy, mode, stress_scenarios, model, scenario, include_suggestions
            )

    def _analyze(self, case, policy, mode, stress_scenarios, model, scenario, include_suggestions):
        if mode not in {"real", "demonstration"}:
            raise ValueError("Mode inconnu")
        if mode == "demonstration" and case.data_classification != "synthetic":
            raise ValueError("Le mode démonstration exige des données explicitement synthétiques")
        if policy:
            authorize_policy(policy, self.core, mode, case.data_classification)
            profile = getattr(case, "profile", getattr(case, "mode", None))
            if profile not in policy.profiles:
                raise ValueError("Profil non couvert par la politique")
            if case.analysis_details.funding.product_id != policy.product.id:
                raise ValueError("Produit non couvert par la politique")
            if policy.validation_status == "approved" and (
                case.analysis_details.as_of is None
                or policy.approval.approved_on > case.analysis_details.as_of
            ):
                raise ValueError(
                    "Date de référence et politique approuvée à cette date nécessaires"
                )
        effective, normalization = effective_case(case)
        financial = self.calculator(effective, scenario)
        ctx = AnalysisContext(case, financial)
        stresses = (
            stress_scenarios
            if stress_scenarios is not None
            else policy.demonstration_stresses
            if policy and mode == "demonstration"
            else []
        )
        stress_results = [(s, self.calculator(effective, s)) for s in stresses]
        if scenario is not None:
            stress_results = [(scenario, financial)] + stress_results
        sections = self.sections(ctx, policy, stress_results)
        timing = analyze_timing(ctx)
        scoring = score_report(ctx, sections, policy, mode, model)
        suggestions = (
            suggest(
                ctx, sections, policy, lambda alternative: self.calculate(alternative, scenario)
            )
            if include_suggestions
            else []
        )
        risk = financial_risk(financial, timing)
        missing = sorted(
            set(
                [m for s in sections for m in s.missing_information]
                + financial.information_requested
                + timing["information_requested"]
            )
        )
        if (
            any(p.basis == "forecast" for p in case.periods)
            and not case.analysis_details.projection_assumptions
        ):
            missing.append("Hypothèses explicites des projections à justifier")
        documentary = sections[0]
        review = bool(
            risk["period_deficits"]
            or risk["negative_balance_periods"]
            or (timing["minimum_balance"] is not None and timing["minimum_balance"] < 0)
        )
        if policy:
            review = (
                review
                or ("incomplete_sections" in policy.mandatory_review and bool(missing))
                or (
                    "documentary_alert" in policy.mandatory_review
                    and (bool(documentary.alerts) or documentary.status == "incomplet")
                )
            )
        states = []
        if review:
            states.append("revue_approfondie_requise")
        if missing:
            states.append("dossier_a_completer")
        if any(
            s.simulated_effect and s.simulated_effect.get("status") == "available"
            for s in suggestions
        ):
            states.append("simulation_alternative_disponible")
        states.append("analyse_disponible")
        scoring["mandatory_review"] = review
        comparisons = []
        baseline_for_comparison = self.calculator(effective) if scenario else financial
        for stress, result in stress_results:
            comparisons.append(
                {
                    "kind": "stress",
                    "assumptions": stress.model_dump(mode="json"),
                    **compare_financial(baseline_for_comparison, result),
                }
            )
        assumptions = [
            "Montants XOF, centième ROUND_HALF_UP ; ratios en Decimal, précision 28, affichage technique à 8 décimales.",
            "Aucune moyenne historique prolongée automatiquement ; seuls les flux explicitement fournis sont projetés.",
            "Aucune donnée documentaire non revue admise automatiquement dans les calculs.",
        ] + normalization
        assumptions.extend(n.text for n in case.analysis_details.projection_assumptions)
        if self.core == "businesses":
            assumptions.append(
                "Les stress de ventes portent sur les encaissements : répercussion proportionnelle supposée, sans recalcul d’un résultat comptable historique."
            )
        if any(p.basis == "forecast" for p in case.periods):
            assumptions.append(
                "Des flux prévisionnels sont présents : résultats conditionnels, pas de recettes garanties."
            )

        if scenario:
            assumptions.append("Scénario appliqué aux calculs : " + scenario.model_dump_json())
        return AssessmentReport(
            engine_version=ENGINE_VERSION,
            core=self.core,
            operating_state=states[0],
            operating_states=states,
            summary=summary(self.core, risk, missing, review, scoring),
            sections=sections,
            major_alerts=[a for s in sections for a in s.alerts],
            missing_information=sorted(set(missing)),
            financial_risk=risk,
            documentary_quality={
                **financial.documentary_quality,
                "status": documentary.status,
                "authenticity_status": "not_assessed",
                "notice": "Une incohérence demande vérification ; aucune fraude automatiquement déduite.",
            },
            scoring=scoring,
            suggestions=suggestions,
            comparisons=comparisons,
            financing_conditions=loan_summary(case.requested_loan, ctx.reader),
            financial_calculations=financial.model_dump(mode="json"),
            assumptions=assumptions,
            sources=[e.model_dump(mode="json") for e in case.evidence],
            versions={
                "engine": ENGINE_VERSION,
                "financial_engine": FINANCIAL_ENGINE_VERSION,
                "rules": "financial-facts-1",
                "policy": policy.id + ":" + policy.version if policy else None,
                "mode": mode,
                "combination": "dual-70-30-v1",
            },
            policy_snapshot=policy.model_dump(mode="json") if policy else None,
            human_validations=[e.model_dump(mode="json") for e in case.evidence if e.review_id],
        )


class IndividualAnalysisEngine(BaseAnalysisEngine):
    core = "individuals"
    calculator = staticmethod(individual_calculate)

    def sections(self, ctx, policy, stresses):
        return [
            individual_sections.identity(ctx),
            individual_sections.income(ctx),
            individual_sections.budget(ctx),
            individual_sections.debt(ctx),
            individual_sections.capacity(ctx),
            individual_sections.reserve(ctx, stresses),
            individual_sections.financing(ctx, policy),
        ]


class BusinessAnalysisEngine(BaseAnalysisEngine):
    core = "businesses"
    calculator = staticmethod(business_calculate)

    def sections(self, ctx, policy, stresses):
        return [
            business_sections.identity(ctx, business=True),
            business_sections.activity(ctx),
            business_sections.profitability(ctx),
            business_sections.working_capital(ctx),
            business_sections.treasury(ctx),
            business_sections.debt(ctx, business=True),
            business_sections.capacity(ctx, business=True),
            business_sections.project(ctx, policy, stresses),
            business_sections.collateral(ctx),
        ]
