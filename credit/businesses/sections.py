from decimal import Decimal
from credit.shared.calculation import total
from credit.assessment.context import ratio
from credit.assessment.common_sections import identity, debt, capacity, financing


def activity(ctx):
    s = ctx.section("activity", "Activité et modèle économique")
    for path in [
        "activity",
        "analysis_details.counterparties",
        "historical_cashflows",
        "analysis_details.dependencies",
        "analysis_details.seasonality",
    ]:
        ctx.use(s, path)
    customers = {}
    denominators = []
    if not ctx.details.customer_receipts_complete:
        s.missing_information.append(
            "Ventilation complète des encaissements par client pour calculer la concentration"
        )
    coherent = ctx.details.customer_receipts_complete
    for p in ctx.case.periods:
        amount = ctx.money(s, f"receipts.{p.period}", p.receipts)
        selected = [
            c
            for c in ctx.details.counterparties
            if c.period == p.period and c.role == "customer" and c.flow_kind == "receipt"
        ]
        amounts = []
        for c in selected:
            value = ctx.money(s, "customer_receipt." + c.name, c.amount)
            amounts.append(value)
            customers[c.name] = (
                None
                if value is None or customers.get(c.name, Decimal(0)) is None
                else customers.get(c.name, Decimal(0)) + value
            )
        if ctx.details.customer_receipts_complete and total(amounts) != amount:
            coherent = False
            s.missing_information.append(f"Rapprocher encaissements et clients en {p.period}")
        denominators.append(amount)
    for row in ctx.financial.periods:
        ctx.metric(
            s,
            "retained_receipts_" + str(row.period),
            row.operating_receipts,
            "XOF",
            "Encaissements retenus après hypothèses explicites ; commandes et factures exclues",
            row.period,
        )
    concentration = (
        ratio(max(customers.values()), total(denominators))
        if coherent and customers and all(v is not None for v in customers.values())
        else None
    )
    ctx.metric(
        s,
        "largest_customer_share",
        concentration,
        "ratio",
        "Maximum des encaissements d’un client / encaissements totaux rapprochés ; commandes et factures exclues",
    )
    history = [
        ctx.money(s, "historical_receipts." + str(p.period), p.receipts)
        for p in ctx.case.historical_cashflows
    ]
    cv = None
    if len(history) >= 3 and all(v is not None for v in history) and total(history) > 0:
        mean = total(history) / len(history)
        cv = ratio((sum((v - mean) ** 2 for v in history) / len(history)).sqrt(), mean)
    ctx.metric(
        s,
        "receipts_history_cv",
        cv,
        "ratio",
        "Variabilité des encaissements historiques ; ne prouve pas à elle seule une saisonnalité annuelle",
    )
    if not ctx.details.dependencies:
        s.missing_information.append(
            "Principaux fournisseurs et dépendances opérationnelles documentées"
        )
    if not ctx.details.seasonality:
        s.missing_information.append(
            "Calendrier saisonnier et portefeuille de commandes à documenter"
        )
    if concentration == 1:
        s.alerts.append(
            "Tous les encaissements rapprochés dépendent d’un client ; vérifier contrats, délais et suivi."
        )
        s.status = "vigilance"
    return ctx.finish(
        s,
        "Commandes, factures et encaissements réels sont identifiés séparément. Seuls les encaissements contribuent à la trésorerie du noyau direct.",
    )


def profitability(ctx):
    s = ctx.section("profitability", "Rentabilité")
    ctx.use(s, "analysis_details.accounting")
    accounting = ctx.details.accounting
    if not accounting:
        s.missing_information.append(
            "Comptes de résultat structurés, périodes et unités nécessaires ; les flux de caisse ne sont pas un résultat comptable"
        )
    turnover_values = []
    net_margins = []
    for i, p in enumerate(accounting):
        prefix = f"accounting.{i}"
        unit = p.unit_multiplier
        revenue = ctx.money(s, prefix + ".turnover", p.turnover, multiplier=unit)
        opex = ctx.money(s, prefix + ".operating_expenses", p.operating_expenses, multiplier=unit)
        cogs = (
            ctx.money(s, prefix + ".cost_of_sales", p.cost_of_sales, multiplier=unit)
            if p.cost_of_sales is not None
            else None
        )
        computed = (
            None
            if revenue is None
            or opex is None
            or (p.costs_definition == "excluding_cost_of_sales" and cogs is None)
            else revenue - opex - (cogs if p.costs_definition == "excluding_cost_of_sales" else 0)
        )
        operating = (
            ctx.money(s, prefix + ".operating_result", p.operating_result, multiplier=unit)
            if p.operating_result is not None
            else computed
        )
        if computed is not None and operating is not None and computed != operating:
            s.missing_information.append(
                prefix + " : rapprocher le résultat d’exploitation et les coûts"
            )
            operating = None
        net = ctx.money(s, prefix + ".net_result", p.net_result, multiplier=unit)
        gross = ratio(None if revenue is None or cogs is None else revenue - cogs, revenue)
        net_margin = ratio(net, revenue)
        ctx.metric(
            s,
            f"turnover_{i}",
            revenue,
            "XOF",
            "Chiffre d’affaires × multiplicateur d’unité explicitement fourni",
            p.end,
        )
        ctx.metric(
            s,
            f"gross_margin_{i}",
            gross,
            "ratio",
            "(Chiffre d’affaires − coût des ventes) / chiffre d’affaires",
            p.end,
        )
        ctx.metric(
            s,
            f"operating_result_{i}",
            operating,
            "XOF",
            "CA − coûts des ventes − charges hors coût des ventes ; ou CA − charges incluant déjà ces coûts",
            p.end,
        )
        ctx.metric(
            s,
            f"net_result_{i}",
            net,
            "XOF",
            "Résultat net comptable fourni et rapproché, pas une déduction des seuls flux de caisse",
            p.end,
        )
        ctx.metric(
            s,
            f"net_margin_{i}",
            net_margin,
            "ratio",
            "Résultat net / chiffre d’affaires strictement positif",
            p.end,
        )
        ctx.fact(
            s,
            f"nonnegative_result_{i}",
            f"net_result_{i}",
            "ge",
            message=f"Resultat net négatif pour la période se terminant le {p.end}.",
        )
        turnover_values.append(revenue)
        net_margins.append(net_margin)
    growth = None
    if len(accounting) >= 2:
        first, last = accounting[-2:]
        before, after = turnover_values[-2:]
        days_before = Decimal((first.end - first.start).days + 1)
        days_after = Decimal((last.end - last.start).days + 1)
        if days_before == days_after or ctx.details.accounting_comparison == "daily_rate":
            if ctx.details.accounting_comparison == "daily_rate":
                before = None if before is None else before / days_before
                after = None if after is None else after / days_after
            growth = ratio(None if before is None or after is None else after - before, before)
        else:
            s.missing_information.append(
                "Périodes comptables de durées différentes : fournir une comparaison normalisée explicite"
            )
    ctx.metric(
        s,
        "turnover_growth",
        growth,
        "ratio",
        "(CA comparable après − CA comparable avant) / CA avant ; normalisation journalière seulement si explicitement demandée",
    )
    ctx.metric(
        s,
        "net_margin",
        net_margins[-1] if net_margins else None,
        "ratio",
        "Dernière marge nette comptable calculable, sans comparaison implicite de durées",
    )
    return ctx.finish(
        s,
        "Les pertes et résultats sont signés. Les unités sont converties explicitement ; une unité inconnue bloque le calcul, sans supposer des francs ou des milliers.",
    )


def working_capital(ctx):
    s = ctx.section("working_capital", "Cycle d’exploitation et besoin en fonds de roulement")
    ctx.use(s, "analysis_details.working_capital")
    if ctx.details.working_capital_applicable is False:
        if any(
            a is not None and a.value not in (None, 0)
            for a in [ctx.case.inventory, ctx.case.receivables, ctx.case.payables]
        ):
            s.missing_information.append(
                "Non-applicabilité du BFR contradictoire avec des postes de bilan renseignés"
            )
        else:
            s.status = "non_applicable"
            return ctx.finish(
                s,
                "Absence de cycle stock/créances/fournisseurs explicitement déclarée ; aucun poids redistribué.",
            )
    wc = ctx.details.working_capital
    if wc is None:
        s.missing_information.append(
            "Stocks, créances et fournisseurs à une même date, puis données moyennes et flux de période pour les délais"
        )
        return ctx.finish(
            s, "Une variation de BFR n’est jamais retranchée de nouveau des flux directs."
        )
    values = {
        k: ctx.money(s, "working_capital." + k, getattr(wc, k))
        for k in ["inventory", "receivables", "payables"]
    }
    bfr = (
        None
        if any(v is None for v in values.values())
        else values["inventory"] + values["receivables"] - values["payables"]
    )
    ctx.metric(
        s,
        "working_capital",
        bfr,
        "XOF",
        "Stocks + créances clients − dettes fournisseurs, à la même date",
        wc.as_of,
    )
    days = Decimal((wc.period_end - wc.period_start).days + 1) if wc.period_start else None
    for id, average, denominator in [
        ("dso", "average_receivables", "credit_sales"),
        ("dpo", "average_payables", "credit_purchases"),
        ("dio", "average_inventory", "cost_of_sales"),
    ]:
        numerator = ctx.money(s, "working_capital." + average, getattr(wc, average))
        denom = ctx.money(s, "working_capital." + denominator, getattr(wc, denominator))
        value = ratio(numerator, denom)
        value = None if value is None or days is None else value * days
        ctx.metric(
            s,
            id,
            value,
            "jours",
            f"{average} / {denominator} × jours de la période ; moyennes obligatoires",
        )
        if value is None:
            s.missing_information.append(
                "Données de période et dénominateur positif requis pour " + id
            )
    for key in ["overdue_receivables", "overdue_payables"]:
        value = ctx.money(s, "working_capital." + key, getattr(wc, key))
        ctx.metric(
            s, key, value, "XOF", "Montants échus non réglés explicitement fournis", wc.as_of
        )
        if value and value > 0:
            s.alerts.append("Retards de règlement : " + key)
    return ctx.finish(
        s,
        "Les délais ne sont pas fabriqués à partir de soldes seuls. L’analyse BFR est informative : aucune seconde déduction dans la trésorerie directe.",
    )


def treasury(ctx):
    s = ctx.section("treasury", "Trésorerie")
    ctx.use(s, "opening_cash")
    ctx.use(s, "periods")
    for row in ctx.financial.periods:
        ctx.metric(
            s,
            "closing_cash_" + str(row.period),
            row.closing_cash,
            "XOF",
            "Trésorerie début + marge après dette + crédit reçu − emplois financés",
            row.period,
        )
        if row.closing_cash is None:
            s.missing_information.append("Flux de trésorerie inconnus en " + str(row.period))
    ctx.metric(
        s,
        "minimum_cash",
        ctx.financial.financial_findings.minimum_balance,
        "XOF",
        "Minimum des soldes de fin de période ; date conservée dans les calculs financiers",
    )
    ctx.fact(
        s,
        "cash_nonnegative",
        "minimum_cash",
        "ge",
        message="Trésorerie projetée négative : tension de liquidité malgré une rentabilité éventuellement positive.",
    )
    return ctx.finish(
        s,
        "Encaissements d’exploitation, nouveaux financements et emplois des fonds sont séparés. Les prélèvements du ménage déjà inclus dans l’exploitation ne sont pas déduits une seconde fois.",
    )


def project(ctx, policy=None, stress_results=()):
    section = financing(ctx, policy, business=True)
    for i, (scenario, result) in enumerate(stress_results):
        value = result.financial_findings.minimum_balance
        ctx.metric(
            section,
            f"stress_cash_{i}",
            value,
            "XOF",
            "Trésorerie minimale recalculée : " + scenario.name,
        )
        if result.financial_findings.deficit_periods:
            section.alerts.append("Marge périodique déficitaire sous " + scenario.name)
        if value is not None and value < 0:
            section.alerts.append("Trésorerie négative sous " + scenario.name)
    if not stress_results:
        section.missing_information.append(
            "Scénarios de ventes, coûts, retard client ou démarrage à préciser"
        )
    return ctx.finish(
        section,
        section.explanation
        + " Les recettes attendues ne deviennent pas certaines parce qu’elles figurent au prévisionnel.",
    )


def collateral(ctx):
    s = ctx.section("collateral", "Garanties et recouvrement", "collateral")
    ctx.use(s, "analysis_details.collateral")
    if ctx.details.collateral_applicable is False and not ctx.details.collateral:
        s.status = "non_applicable"
        return ctx.finish(
            s, "Aucune garantie proposée explicitement ; aucune valeur de recouvrement supposée."
        )
    if not ctx.details.collateral:
        s.missing_information.append(
            "Garanties proposées ou déclaration explicite de non-applicabilité"
        )
    for i, item in enumerate(ctx.details.collateral):
        value = ctx.money(s, f"collateral.{i}.declared_value", item.declared_value)
        charges = ctx.money(s, f"collateral.{i}.known_charges", item.known_charges)
        ctx.metric(
            s,
            f"declared_collateral_{i}",
            value,
            "XOF",
            "Valeur déclarée, jamais assimilée à un recouvrement certain",
            item.valuation_date,
        )
        ctx.metric(
            s,
            f"known_charges_{i}",
            charges,
            "XOF",
            "Charges connues, sans présumer leur exhaustivité",
            item.valuation_date,
        )
        if item.valuation_date is None:
            s.missing_information.append("Date d’évaluation de " + item.description)
        if not item.verification:
            s.missing_information.append("Vérifications restantes sur " + item.description)
        if not item.realization_limits:
            s.missing_information.append(
                "Délais, coûts et limites de réalisation de " + item.description
            )
    return ctx.finish(
        s,
        "Une garantie ne corrige pas une insuffisance de capacité de paiement. Aucun taux de récupération ou LGD n’est dérivé de la valeur déclarée.",
    )


BUSINESS_SECTIONS = (
    identity,
    activity,
    profitability,
    working_capital,
    treasury,
    debt,
    capacity,
    project,
    collateral,
)
