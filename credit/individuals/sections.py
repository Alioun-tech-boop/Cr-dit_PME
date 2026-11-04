from decimal import Decimal
from credit.shared.calculation import total
from credit.assessment.context import ratio
from credit.assessment.common_sections import identity, debt, capacity, financing


def income(ctx):
    s = ctx.section("income", "Revenus et stabilité")
    for path in ["periods", "income_history", "analysis_details.continuity"]:
        ctx.use(s, path)
    shares = []
    for p in ctx.case.periods:
        sources = {}
        for i, item in enumerate(p.incomes):
            value = ctx.money(s, f"incomes.{p.period}.{i}", item.net)
            sources[item.source] = (
                None
                if value is None or sources.get(item.source, Decimal(0)) is None
                else sources.get(item.source, Decimal(0)) + value
            )
            if item.kind == "self_employed_net":
                if not item.professional_costs_already_deducted and item.activity_receipts is None:
                    s.missing_information.append(
                        "Justifier les coûts professionnels et le revenu personnel net de "
                        + item.source
                    )
                if item.activity_receipts is not None:
                    gross = ctx.money(s, "activity_receipts", item.activity_receipts)
                    costs = ctx.money(s, "professional_costs", item.necessary_professional_costs)
                    ctx.metric(
                        s,
                        "self_employed_net_" + str(p.period),
                        None if gross is None or costs is None else gross - costs,
                        "XOF",
                        "Encaissements d’activité − coûts professionnels nécessaires",
                        p.period,
                    )
        net = total(sources.values())
        ctx.metric(
            s,
            "net_by_source_total_" + str(p.period),
            net,
            "XOF",
            "Somme des revenus personnels nets par source, avant neutralisation globale des retenues",
            p.period,
        )
        if net and all(v is not None for v in sources.values()):
            shares.append(max(sources.values()) / net)
        if len(sources) == 1:
            s.alerts.append(
                f"{p.period} : dépendance à une seule source déclarée ; continuité à documenter."
            )
    for row in ctx.financial.periods:
        ctx.metric(
            s,
            "retained_net_" + str(row.period),
            row.net_retained_income,
            "XOF",
            "Nets retenus après neutralisation des retenues et hypothèses explicites du scénario",
            row.period,
        )
    cv = ctx.financial.financial_findings.income_variability_cv
    ctx.metric(
        s,
        "history_cv",
        cv,
        "ratio",
        "Écart type de population / moyenne sur au moins trois revenus historiques comparables, moyenne > 0",
    )
    if cv is None:
        s.missing_information.append(
            "Au moins trois observations historiques de revenus comparables, de moyenne positive"
        )
    ctx.metric(
        s,
        "largest_source_share",
        max(shares) if shares else None,
        "ratio",
        "Maximum du poids d’une source dans les revenus nets déclarés de chaque période",
    )
    for p in ctx.case.income_history:
        if p.net_personal_income.value == 0:
            s.alerts.append(
                f"Interruption de revenu observée en {p.period} ; pas de moyenne prolongée automatiquement."
            )
    if not ctx.details.continuity:
        s.missing_information.append(
            "Justificatifs de continuité des revenus : contrat, pension ou activité nette"
        )
    if s.alerts:
        s.status = "vigilance"
    return ctx.finish(
        s,
        "Chiffre d’affaires et revenu personnel ne sont pas confondus. Les revenus par période restent distincts de leur stabilité ; aucune continuité future n’est garantie.",
    )


def budget(ctx):
    s = ctx.section("budget", "Dépenses essentielles et budget du ménage")
    ctx.use(s, "analysis_details.expenses")
    for i, p in enumerate(ctx.case.periods):
        ctx.use(s, f"periods.{i}.essential_expenses")
        value = ctx.money(s, f"essential_expenses.{p.period}", p.essential_expenses)
        included = [e for e in ctx.details.expenses if e.period == p.period and e.included_in_total]
        extra = [
            e for e in ctx.details.expenses if e.period == p.period and not e.included_in_total
        ]
        additional = total(
            ctx.money(s, f"extra_essential.{p.period}.{j}", e.amount) for j, e in enumerate(extra)
        )
        retained = None if value is None or additional is None else value + additional
        ctx.metric(
            s,
            "essential_" + str(p.period),
            retained,
            "XOF",
            "Total déclaré + dépenses nécessaires hors total, une seule fois",
            p.period,
        )
        if ctx.details.expense_breakdown_complete:
            breakdown = total(
                ctx.money(s, f"expense_breakdown.{p.period}.{j}", e.amount)
                for j, e in enumerate(included)
            )
            if breakdown != value:
                s.missing_information.append(
                    f"Rapprocher le détail et le total des dépenses essentielles en {p.period}"
                )
    for row in ctx.financial.periods:
        retained = (
            None
            if row.net_retained_income is None or row.available_before_debt is None
            else row.net_retained_income - row.available_before_debt
        )
        ctx.metric(
            s,
            "retained_essential_" + str(row.period),
            retained,
            "XOF",
            "Charges essentielles retenues dans le calcul, y compris coûts hors total et stress explicite",
            row.period,
        )
    if not ctx.details.expense_breakdown_complete:
        s.missing_information.append(
            "Ventilation du logement, charges récurrentes, irrégulières et obligations du ménage"
        )
    s.strengths.append(
        "Les dépenses essentielles ne sont jamais réduites pour améliorer artificiellement les ratios."
    )
    return ctx.finish(
        s,
        "Les dépenses connues à venir sont intégrées dans leur période lorsqu’elles sont explicitement hors total ; les postes déjà inclus ne sont pas déduits deux fois.",
    )


def reserve(ctx, stress_results=()):
    s = ctx.section("reserve", "Réserve et résistance aux difficultés")
    ctx.use(s, "mobilizable_reserve")
    ctx.use(s, "analysis_details.blocked_savings")
    opening = ctx.money(s, "mobilizable_reserve", ctx.case.mobilizable_reserve)
    expenses = [
        None
        if r.net_retained_income is None or r.available_before_debt is None
        else r.net_retained_income - r.available_before_debt
        for r in ctx.financial.periods
    ]
    max_expense = max(expenses) if expenses and all(v is not None for v in expenses) else None
    ctx.metric(
        s,
        "reserve_months",
        ratio(opening, max_expense),
        "périodes de dépenses essentielles",
        "Réserve mobilisable initiale / dépenses essentielles maximales d’une période ; pas un revenu",
    )
    ctx.metric(
        s,
        "minimum_reserve",
        ctx.financial.financial_findings.minimum_balance,
        "XOF",
        "Minimum des réserves projetées de fin de période",
    )
    if (
        opening is None
        or max_expense is None
        or ctx.financial.financial_findings.minimum_balance is None
    ):
        s.missing_information.append(
            "Réserve mobilisable et flux de toutes les périodes nécessaires à la projection"
        )
    ctx.fact(
        s,
        "nonnegative_reserve",
        "minimum_reserve",
        "ge",
        message="Réserve projetée négative : les déficits ne sont pas couverts par les fonds mobilisables.",
    )
    if ctx.details.blocked_savings is None:
        s.missing_information.append(
            "Distinguer l’épargne bloquée ou indisponible de la réserve mobilisable"
        )
    if not stress_results:
        s.missing_information.append(
            "Scénarios explicites de baisse de revenu, hausse de charges ou retard à fournir"
        )
    for i, (scenario, result) in enumerate(stress_results):
        value = result.financial_findings.minimum_balance
        ctx.metric(
            s,
            f"stress_reserve_{i}",
            value,
            "XOF",
            "Réserve minimale recalculée sous les hypothèses du scénario " + scenario.name,
        )
        margin_values = [r.margin_after_debt for r in result.periods]
        min_margin = (
            min(margin_values)
            if margin_values and all(v is not None for v in margin_values)
            else None
        )
        ctx.metric(
            s,
            f"stress_margin_{i}",
            min_margin,
            "XOF",
            "Marge minimale sous le scénario " + scenario.name,
        )
        if result.financial_findings.deficit_periods:
            s.alerts.append(
                "Marge déficitaire sous "
                + scenario.name
                + " ; réserve ponctuelle et continuité à vérifier."
            )
        if value is not None and value < 0:
            s.alerts.append("Réserve insuffisante sous le scénario " + scenario.name)
    if s.alerts and s.status == "favorable":
        s.status = "vigilance"
    return ctx.finish(
        s,
        "L’épargne bloquée est présentée séparément et exclue du disponible. La réserve ponctuelle peut couvrir une tension temporaire, jamais remplacer durablement un revenu.",
    )


INDIVIDUAL_SECTIONS = (identity, income, budget, debt, capacity, reserve, financing)
