"""Adaptation explicite, en lecture seule, des instantanés métier vers le document."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from credit.printing.catalog import CATALOG, ANALYSIS_TEMPLATES
from credit.printing.contracts import Presentation, Section, Table

MONTHS = [
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
]
LABELS = {
    "requested_loan": "Crédit demandé",
    "professional_costs_already_deducted": "Coûts professionnels déjà déduits",
    "amortization_method": "Méthode d’amortissement",
    "loan_reference": "Référence du prêt",
    "arrears": "Arriérés",
    "days_past_due": "Jours de retard",
    "restructuring_count": "Nombre de restructurations",
    "category": "Catégorie",
    "frequency": "Fréquence",
    "amount": "Montant",
    "included_in_total": "Déjà inclus dans le total",
    "name": "Nom / dénomination",
    "profile": "Profil",
    "household_scope": "Périmètre du ménage",
    "currency": "Devise",
    "period": "Période",
    "basis": "Nature des données",
    "source": "Source",
    "net": "Revenu personnel net",
    "incomes": "Revenus",
    "essential_expenses": "Dépenses essentielles",
    "mobilizable_reserve": "Réserve mobilisable",
    "payroll_loan_treatment": "Traitement des retenues de prêts",
    "payroll_loan_deductions": "Retenues de prêts",
    "principal": "Capital",
    "interest": "Intérêts",
    "fees": "Frais",
    "annual_nominal_rate": "Taux nominal annuel (fraction)",
    "description": "Description",
    "reference": "Référence",
    "due_date": "Date d’exigibilité",
    "schedule": "Échéancier",
    "activity": "Activité",
    "mode": "Mode de données",
    "opening_cash": "Trésorerie initiale disponible",
    "receipts": "Encaissements d’exploitation",
    "operating_expenses": "Dépenses d’exploitation",
    "taxes": "Impôts et autres sorties",
    "essential_investments": "Investissements indispensables",
    "household_withdrawals": "Prélèvements ménage",
    "household_included_in_operating": "Prélèvements déjà inclus dans les dépenses",
    "requested_loan_disbursement": "Décaissement du nouveau financement",
    "financed_uses": "Emplois du financement",
    "receivables": "Créances clients",
    "payables": "Dettes fournisseurs",
    "inventory": "Stocks",
    "as_of": "Date de référence",
    "unit_multiplier": "Multiplicateur d’unité comptable",
    "turnover": "Chiffre d’affaires",
    "operating_result": "Résultat d’exploitation",
    "net_result": "Résultat net",
    "cost_of_sales": "Coût des ventes",
    "equity": "Fonds propres",
    "start": "Début",
    "end": "Fin",
    "address": "Adresse",
    "telephone": "Téléphone",
    "email": "Courriel",
    "identity_reference": "Référence d’identité déclarée",
    "legal_form": "Forme juridique",
    "representatives": "Représentants",
    "role": "Qualité",
    "authority_reference": "Référence du mandat",
    "applicant_comments": "Commentaire du demandeur",
    "internal_observations": "Observations internes",
    "funding": "Financement du projet",
    "justified_need": "Besoin justifié",
    "announced_contribution": "Apport annoncé",
    "verified_contribution": "Apport contrôlé",
    "product_id": "Produit",
    "purpose": "Objet",
    "implementation_start": "Démarrage prévu",
    "expected_start": "Démarrage attendu",
    "margin_after_credit": "Marge après crédit",
    "margin_after_debt": "Marge après dette",
    "projected_reserve": "Réserve projetée",
    "closing_cash": "Trésorerie finale",
    "net_retained_income": "Revenus nets retenus",
    "available_before_debt": "Disponible avant dettes",
    "new_debt_service": "Service de la nouvelle dette",
    "available_before_debts": "Disponible avant dettes",
    "operating_receipts": "Encaissements d’exploitation retenus",
    "cash_available_for_debt": "Trésorerie disponible pour la dette",
    "minimum_margin_before": "Marge minimale initiale",
    "minimum_margin_after": "Marge minimale simulée",
    "minimum_margin_change": "Variation de marge minimale",
    "minimum_balance_before": "Solde minimal initial",
    "minimum_balance_after": "Solde minimal simulé",
    "margin_before": "Marge initiale",
    "margin_after": "Marge simulée",
    "balance_after": "Solde simulé",
    "first_instalment": "Première échéance",
    "maximum_instalment": "Échéance maximale",
    "total_repayment": "Remboursement total",
    "total_credit_cost": "Coût total (intérêts et frais)",
    "payment_count": "Nombre d’échéances",
    "first_due": "Première échéance (date)",
    "last_due": "Dernière échéance (date)",
    "total_cost": "Coût total (intérêts et frais)",
    "duration_months": "Durée (mois)",
    "instalments": "Nombre d’échéances",
    "minimum_margin": "Marge minimale",
    "minimum_balance": "Solde minimal",
    "minimum_balance_date": "Date du solde minimal",
    "period_deficits": "Périodes déficitaires",
    "negative_balance_periods": "Périodes à solde négatif",
    "existing_debt_service": "Service des dettes existantes",
    "requested_debt_service": "Service du crédit demandé",
    "debt_service_ratio": "Poids des échéances dans les revenus",
    "debt_service_coverage": "Couverture du service de dette",
    "revenue_drop": "Baisse de revenus / encaissements (fraction)",
    "expense_increase": "Hausse des dépenses (fraction)",
    "delay_amount": "Encaissement retardé",
    "delay_from": "Période initiale",
    "delay_to": "Période de report",
    "months": "Durée (mois)",
    "kind": "Type",
    "status": "Statut",
    "financial_comparison": "Comparaison financière",
}
WORDS = {
    "salary": "Salaire",
    "pension": "Pension",
    "self_employed_net": "Revenu personnel net d’activité",
    "housing": "Logement",
    "food": "Alimentation",
    "transport": "Transport",
    "recurring": "Récurrent",
    "irregular": "Irrégulier",
    "future": "À venir",
    "known": "Valeur connue",
    "unknown": "Inconnu",
    "not_applicable": "Non applicable",
    "estimated": "Estimé",
    "declared": "Déclaré",
    "verified": "Contrôlé (sans authentification)",
    "unverified_extracted": "Extrait non contrôlé",
    "contradictory": "Contradictoire",
    "missing": "Manquant",
    "observed": "Observé",
    "forecast": "Prévision",
    "employee": "Salarié",
    "retired": "Retraité",
    "self_employed": "Indépendant",
    "favorable": "Favorable",
    "vigilance": "Vigilance",
    "defavorable": "Défavorable",
    "incomplet": "Incomplet",
    "structured_accounts": "Comptabilité structurée",
    "reconstructed_cashflows": "Flux reconstitués",
    "before_loan_deductions": "Net avant retenues de prêts",
    "after_loan_deductions": "Net après retenues de prêts",
    "unclear": "Traitement à clarifier",
    "not_available": "Indisponible",
    "illustrative_not_validated": "ILLUSTRATIF — NON VALIDÉ",
    "approved": "Politique approuvée",
    "dossier_a_completer": "Dossier à compléter",
    "analyse_disponible": "Analyse disponible",
    "revue_approfondie_requise": "Revue approfondie requise",
    "simulation_alternative_disponible": "Simulation alternative disponible",
    "payment_pressure": "Tension de paiement",
    "incomplete": "Incomplet",
    "no_deficit_in_supplied_flows": "Aucun déficit dans les flux fournis",
    "not_assessed": "Non évaluée",
    "monthly_constant": "Mensualités constantes",
    "explicit": "Échéancier explicite",
    "haute": "Haute",
    "moyenne": "Moyenne",
    "basse": "Basse",
    "analyste": "Analyste",
    "preteur": "Prêteur",
    "demandeur": "Demandeur",
}


def label(key):
    return LABELS.get(key, key.replace("_", " ").capitalize())


def french_date(value):
    try:
        day = date.fromisoformat(str(value)[:10])
        return f"{day.day} {MONTHS[day.month - 1]} {day.year}"
    except ValueError:
        return str(value)


def number(value, decimals=2):
    try:
        n = Decimal(str(value)).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
        return f"{n:,.{decimals}f}".replace(",", "\u202f").replace(".", ",")
    except (InvalidOperation, TypeError, ValueError):
        return str(value)


def scalar(value):
    if value is None:
        return "Non renseigné / non calculable"
    if isinstance(value, bool):
        return "Oui" if value else "Non"
    if isinstance(value, (date, datetime)) or re.fullmatch(
        r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?", str(value)
    ):
        return french_date(value)
    return WORDS.get(str(value), str(value))


def amount(value, unit="XOF / FCFA", evidence=None):
    if not value or value.get("state") == "unknown":
        return "Inconnu"
    if value.get("state") == "not_applicable":
        return "Non applicable"
    text = number(value.get("value")) + " " + unit
    if value.get("state") == "estimated":
        text += " — Estimé"
    statuses = sorted(
        {
            (evidence or {}).get(k, {}).get("status", "declared")
            for k in value.get("evidence_ids", [])
        }
    )
    text += " — " + ", ".join(WORDS.get(s, s) for s in statuses or ["declared"])
    return text


def rows(value, prefix="", evidence=None, unit="XOF / FCFA", internal=False):
    """Conserve états, périodes et échelles ; jamais de calcul de score ou de flux."""
    result = []
    if isinstance(value, dict):
        if "value" in value and "state" in value:
            return [[prefix, amount(value, unit, evidence)]]
        if "text" in value:
            return [[prefix, str(value["text"])]]
        multiplier = value.get("unit_multiplier", 1)
        child_unit = unit
        if "unit_multiplier" in value:
            child_unit = (
                "XOF / FCFA (unité inconnue)"
                if multiplier is None
                else f"XOF / FCFA × {multiplier}"
            )
        for key, val in value.items():
            if key in {"evidence_ids", "internal_observations"} and not internal:
                continue
            if key == "evidence_ids":
                continue
            money_keys = {
                "principal",
                "first_instalment",
                "maximum_instalment",
                "total_repayment",
                "total_credit_cost",
                "total_cost",
                "minimum_margin_before",
                "minimum_margin_after",
                "minimum_margin_change",
                "minimum_balance_before",
                "minimum_balance_after",
                "margin_before",
                "margin_after",
                "balance_after",
                "minimum_margin",
                "minimum_balance",
                "net_retained_income",
                "available_before_debt",
                "existing_debt_service",
                "new_debt_service",
                "margin_after_credit",
                "projected_reserve",
                "operating_receipts",
                "cash_available_for_debt",
                "margin_after_debt",
                "closing_cash",
                "financing_received",
                "financed_uses",
                "delay_amount",
            }
            if key in money_keys and val is not None and not isinstance(val, (dict, list)):
                val = number(val) + " " + child_unit
            elif key in money_keys and val is None:
                val = "Non calculable — " + child_unit
            result += rows(
                val,
                f"{prefix} — {label(key)}" if prefix else label(key),
                evidence,
                child_unit,
                internal,
            )
    elif isinstance(value, list):
        if not value:
            return [[prefix, "Aucun élément renseigné"]]
        for i, item in enumerate(value, 1):
            result += rows(item, f"{prefix} {i}", evidence, unit, internal)
    else:
        result.append([prefix, scalar(value)])
    return result


def table_section(title, value, evidence=None, internal=False):
    return Section(
        title=title,
        tables=[
            Table(
                columns=["Champ / période", "Valeur"],
                rows=rows(value, evidence=evidence, internal=internal),
            )
        ],
    )


def public_case(case):
    # Liste blanche à la racine, puis suppression des observations internes imbriquées.
    allowed = {
        "name",
        "currency",
        "profile",
        "household_scope",
        "activity",
        "mode",
        "record_details",
        "requested_loan",
        "existing_loans",
        "periods",
        "mobilizable_reserve",
        "opening_cash",
        "receivables",
        "payables",
        "inventory",
        "missing_information",
        "analysis_details",
    }

    def clean(node):
        if isinstance(node, dict):
            return {k: clean(v) for k, v in node.items() if k not in {"internal_observations"}}
        if isinstance(node, list):
            return [clean(v) for v in node]
        return node

    # analysis_details est traité champ par champ par les sections de formulaire ci-dessous.
    return {k: clean(v) for k, v in case.items() if k in allowed}


def form_sections(case, core, template, documents, evidence, internal):
    details = case.get("analysis_details", {})
    profile = case.get("record_details", {})
    sections = {
        "identification": [
            table_section(
                "Identification déclarée",
                {
                    "name": case["name"],
                    "profile": case.get("profile", case.get("mode")),
                    **profile,
                    **(
                        {"household_scope": case.get("household_scope")}
                        if core == "individuals"
                        else {"activity": case.get("activity")}
                    ),
                },
                evidence,
                internal,
            )
        ],
        "credit_request": [
            table_section("Conditions de la demande déclarée", case["requested_loan"], evidence),
            table_section("Objet et financement", details.get("funding", {}), evidence),
        ],
        "debts": [
            table_section("Dettes et échéances déclarées", case["existing_loans"], evidence),
            table_section(
                "Historique de remboursement disponible",
                details.get("repayment_observations", []),
                evidence,
            ),
        ],
        "documents": [
            table_section("Pièces effectivement déposées", documents),
            table_section(
                "Informations et pièces explicitement demandées",
                case.get("missing_information", []),
            ),
        ],
    }
    if core == "individuals":
        income_rows = []
        for period in case["periods"]:
            for income in period["incomes"]:
                income_rows.append(
                    [
                        french_date(period["period"]) + " — " + scalar(period.get("basis")),
                        income["source"] + " — " + scalar(income["kind"]),
                        amount(income["net"], evidence=evidence),
                    ]
                )
        income_section = Section(
            title="Revenus nets par source et période",
            tables=[
                Table(
                    columns=["Période / nature", "Source de revenu", "Revenu personnel net"],
                    rows=income_rows,
                )
            ],
        )
        professional = [
            {
                "period": p["period"],
                **{
                    k: v
                    for k, v in i.items()
                    if k
                    in {
                        "source",
                        "activity_receipts",
                        "necessary_professional_costs",
                        "professional_costs_already_deducted",
                    }
                },
            }
            for p in case["periods"]
            for i in p["incomes"]
            if i["kind"] == "self_employed_net"
        ]
        budget_section = Section(
            title="Budget déclaré, sans réduction des dépenses essentielles",
            tables=[
                Table(
                    columns=[
                        "Période / nature",
                        "Dépenses essentielles",
                        "Retenues de prêts",
                        "Traitement",
                    ],
                    rows=[
                        [
                            french_date(p["period"]) + " — " + scalar(p.get("basis")),
                            amount(p["essential_expenses"], evidence=evidence),
                            amount(p["payroll_loan_deductions"], evidence=evidence),
                            scalar(p["payroll_loan_treatment"]),
                        ]
                        for p in case["periods"]
                    ],
                )
            ],
        )
        sections["income_expenses"] = [income_section, budget_section]
        if professional:
            sections["income_expenses"].append(
                table_section(
                    "Activité indépendante : coûts professionnels et revenu personnel distincts",
                    professional,
                    evidence,
                )
            )
        expense_section = Section(
            title="Ventilation des charges renseignées",
            tables=[
                Table(
                    columns=["Période", "Catégorie / fréquence", "Montant", "Inclus dans le total"],
                    rows=[
                        [
                            french_date(e["period"]),
                            scalar(e["category"]) + " — " + scalar(e["frequency"]),
                            amount(e["amount"], evidence=evidence),
                            scalar(e["included_in_total"]),
                        ]
                        for e in details.get("expenses", [])
                    ],
                )
            ],
        )
        sections["household_budget"] = [
            table_section(
                "Périmètre et réserve",
                {
                    "household_scope": case.get("household_scope"),
                    "mobilizable_reserve": case.get("mobilizable_reserve"),
                },
                evidence,
            ),
            budget_section,
            expense_section,
        ]
    else:
        sections["activity"] = [
            table_section(
                "Présentation déclarée",
                {"activity": case.get("activity"), "mode": case.get("mode")},
                evidence,
            ),
            table_section(
                "Relations commerciales et hypothèses déclarées",
                {k: details.get(k) for k in ["counterparties", "seasonality", "dependencies"]},
                evidence,
            ),
        ]
        sections["financial_declaration"] = [
            Section(
                title="Déclaration financière issue des champs saisis",
                paragraphs=[
                    "Document déclaratif ; ni état financier certifié, ni document émis par une banque."
                ],
            ),
            table_section(
                "Périodes comptables et unités renseignées", details.get("accounting", []), evidence
            ),
        ]
        if not details.get("accounting"):
            sections["financial_declaration"] += [
                table_section(
                    "Situation et flux déclarés disponibles, sans compte de résultat reconstitué",
                    {
                        "opening_cash": case.get("opening_cash"),
                        **{k: case.get(k) for k in ["receivables", "payables", "inventory"]},
                        "periods": case["periods"],
                    },
                    evidence,
                )
            ]
        sections["cashflows"] = [
            table_section(
                "Trésorerie initiale", {"opening_cash": case.get("opening_cash")}, evidence
            ),
            table_section("Encaissements et décaissements par période", case["periods"], evidence),
        ]
        sections["working_capital"] = [
            table_section(
                "Créances, fournisseurs et stocks",
                {
                    "working_capital": details.get("working_capital"),
                    **{k: case.get(k) for k in ["receivables", "payables", "inventory"]},
                },
                evidence,
            )
        ]
        sections["project_budget"] = [
            table_section("Budget et financement déclarés", details.get("funding", {}), evidence),
            table_section(
                "Encaissements prévus du projet", details.get("project_receipts", []), evidence
            ),
            table_section("Hypothèses du projet", case.get("project_assumptions", []), evidence),
        ]
    if template == "complete_file":
        return [
            s
            for group in sections.values()
            for s in group
            if not (core == "individuals" and s is budget_section)
        ] + ([budget_section] if core == "individuals" else [])
    return sections[template]


def suggestions_sections(suggestions, internal):
    sections = []
    for i, s in enumerate(suggestions, 1):
        fields = [
            ["Constat", s["problem"]],
            ["Action proposée", s["action"]],
            ["Destinataire", scalar(s["recipient"])],
            ["Priorité", scalar(s["priority"])],
            ["Prérequis", "\n".join(s["prerequisites"])],
            ["Justificatif / vérification attendu", "\n".join(s["evidence_needed"])],
            ["Coûts, contreparties et limites", "\n".join(s["costs_and_limits"])],
        ]
        effect = s.get("simulated_effect")
        fields += (
            rows(effect, "Effet financier simulé")
            if effect
            else [["Effet financier", "Non calculable avec les données disponibles"]]
        )
        if internal:
            fields += [["Règles et données déclenchantes", "\n".join(s["triggers"])]]
        sections.append(
            Section(
                title=f"Proposition {i}",
                tables=[Table(columns=["Rubrique", "Proposition, sans engagement"], rows=fields)],
            )
        )
    return sections or [
        Section(title="Suggestions", paragraphs=["Aucune suggestion communicable disponible."])
    ]


def analysis_sections(report, template, internal, publication, parent=None, simulation=None):
    sections = []
    if not report:
        return [
            Section(
                title="Analyse indisponible",
                paragraphs=["Aucune analyse disponible ; aucun indicateur ou score ajouté."],
            )
        ]
    available = "sections" in report
    if not internal:
        # Projection autonome : aucune section brute, score, source ou règle dans ce modèle.
        sections = [
            Section(
                title="État de la restitution",
                paragraphs=[
                    "Restitution demandeur. Les constats ne constituent ni un accord de crédit ni une certification."
                ],
            )
        ]
        if not publication.get("financial_results"):
            sections.append(
                Section(
                    title="Résultats non communiqués",
                    paragraphs=[
                        "Les résultats d’analyse nécessitent une autorisation explicite de communication."
                    ],
                )
            )
        else:
            sections.append(
                table_section("Résultats financiers autorisés", public_financial(report))
            )
            if template == "simulation_report":
                sections.append(
                    table_section(
                        "Comparaison avant / après autorisée",
                        report.get("comparisons", report.get("financial_comparison")),
                    )
                )
                sections.append(
                    table_section(
                        "Conditions simulées",
                        report.get("financing_conditions", report.get("terms")),
                    )
                )
        if publication.get("suggestions"):
            public = [
                {k: v for k, v in s.items() if k != "triggers"}
                for s in report.get("suggestions", [])
                if s["recipient"] == "demandeur"
            ]
            sections += suggestions_sections(public, False)
        return sections
    sections.append(
        Section(
            title="Synthèse et état opérationnel",
            paragraphs=[
                report.get("summary", "Simulation incomplète : projections nécessaires."),
                scalar(report.get("operating_state", report.get("status"))),
            ],
        )
    )
    if available:
        sections.append(
            table_section(
                "Évaluation financière et scores disponibles",
                {
                    "État du risque": scalar(report["financial_risk"]["status"]),
                    "Score de solvabilité sur 100 (élevé favorable)": report["scoring"].get(
                        "criteria_score"
                    ),
                    "Validation de la politique": scalar(
                        report["scoring"].get("criteria_validation_status")
                    ),
                    "Indice de risque sur 100 (pas une probabilité)": report["scoring"].get(
                        "risk_index"
                    ),
                    **(
                        {
                            "Qualification conventionnelle": report["scoring"].get("qualification"),
                            "Revue obligatoire": report["scoring"].get("mandatory_review"),
                            "Méthode": "Déterministe ; aucune probabilité de défaut calculée",
                        }
                        if report.get("engine_version") == "financial_analysis_v2"
                        else {
                            "Modèle": scalar(report["scoring"].get("model_status")),
                            "Score combiné 70/30": report["scoring"].get("combined_score"),
                            "Probabilité de défaut": report["scoring"].get(
                                "probability_of_default"
                            ),
                        }
                    ),
                },
            )
        )
    if template == "analysis_summary":
        # Liste courte ; renvoi explicite au rapport détaillé plutôt que troncature silencieuse.
        strengths = [x for s in report.get("sections", []) for x in s.get("strengths", [])]
        alerts = report.get("major_alerts", [])
        missing = report.get("missing_information", [])
        for title, items in [
            ("Points favorables", strengths),
            ("Fragilités majeures", alerts),
            ("Informations manquantes", missing),
        ]:
            paragraphs = [str(x) for x in items[:5]] or ["Aucun élément disponible."]
            if len(items) > 5:
                paragraphs.append(
                    f"{len(items) - 5} autres éléments : consulter le rapport détaillé."
                )
            sections.append(Section(title=title, paragraphs=paragraphs))
        sections.append(
            Section(
                title="Suggestions prioritaires",
                paragraphs=[s["action"] for s in report.get("suggestions", [])[:3]]
                or ["Aucune suggestion disponible."],
            )
        )
        return sections
    if template == "improvement_plan":
        return sections + suggestions_sections(report.get("suggestions", []), True)
    if template == "simulation_report":
        sections.append(table_section("Paramètres modifiés", simulation or {}))
        if parent:
            sections.append(
                table_section(
                    "Conditions initiales", parent.get("financing_conditions", parent.get("terms"))
                )
            )
        sections.append(
            table_section(
                "Conditions simulées, échéance et coût total",
                report.get("financing_conditions", report.get("terms")),
            )
        )
        sections.append(
            table_section(
                "Comparaison chiffrée avant / après",
                report.get("comparisons", report.get("financial_comparison")),
            )
        )
        sections.append(
            Section(title="Contraintes et hypothèses", paragraphs=report.get("assumptions", []))
        )
        sections.append(
            Section(
                title="Vérifications restant nécessaires",
                paragraphs=report.get("missing_information", [])
                or ["Vérifier la faisabilité des nouvelles conditions."],
            )
        )
        return sections
    if report.get("engine_version") == "financial_analysis_v2":
        deep = report["deep_analysis"]
        if deep.get("policy_exceptions"):
            sections.append(
                table_section(
                    "Dérogations tracées sans modification des calculs",
                    deep["policy_exceptions"],
                    internal=True,
                )
            )
        for title, data in [
            ("Statistiques historiques descriptives", deep["history"]),
            ("Rapprochements limités aux comptes fournis", deep["reconciliation"]),
            (
                "Règles de qualification et contraintes produit",
                {"règles": report["scoring"]["rules"], "contraintes": deep["product_constraints"]},
            ),
            (
                "Scénarios explicitement enregistrés",
                [
                    {
                        k: v
                        for k, v in item.items()
                        if k not in {"input_snapshot", "financial_calculations"}
                    }
                    for item in deep["scenarios"]
                ],
            ),
            ("Recherche bornée des seuils de rupture", deep["reverse_tests"]),
            (
                "Variantes de financement testées, sans conseil automatique",
                [
                    {k: v for k, v in item.items() if k != "input_snapshot"}
                    for item in deep["financing_variants"]["variants"]
                ],
            ),
        ]:
            sections.append(table_section(title, data, internal=True))
    for s in report.get("sections", []):
        part = Section(
            title=s["title"] + " — " + scalar(s["status"]), paragraphs=[s["explanation"]]
        )
        part.tables.append(
            Table(
                columns=["Indicateur / période", "Valeur et unité", "Formule / indisponibilité"],
                rows=[
                    [
                        i["id"] + ((" — " + french_date(i["period"])) if i.get("period") else ""),
                        (
                            "Non calculable"
                            if i["value"] is None
                            else number(i["value"], 8 if i["unit"] == "ratio" else 2)
                        )
                        + " "
                        + i["unit"],
                        i["formula"]
                        + ("\n" + i["unavailable_reason"] if i.get("unavailable_reason") else ""),
                    ]
                    for i in s["indicators"]
                ],
            )
        )
        part.tables.append(
            Table(
                columns=["Règle / version", "Évaluation", "Seuil / résultat"],
                rows=[
                    [
                        r["id"] + " / " + r["version"],
                        r["explanation"],
                        f"{r['operator']} {scalar(r.get('threshold'))} ; résultat : {scalar(r.get('passed'))}",
                    ]
                    for r in s["rules"]
                ],
            )
        )
        part.tables.append(
            Table(
                columns=["Donnée / période", "Valeur / nature", "Sources"],
                rows=[
                    [
                        d["path"] + ((" — " + french_date(d["period"])) if d.get("period") else ""),
                        scalar(d["value"])
                        + " — "
                        + scalar(d.get("state"))
                        + ((" — " + scalar(d["basis"])) if d.get("basis") else "")
                        + ((" — " + str(d["unit"])) if d.get("unit") else ""),
                        "\n".join(
                            str(e.get("id", ""))
                            + " — "
                            + str(e.get("source", ""))
                            + (" page " + str(e["page"]) if e.get("page") else "")
                            for e in d["sources"]
                        ),
                    ]
                    for d in s["data_used"]
                ],
            )
        )
        part.paragraphs += (
            ["Point favorable : " + x for x in s["strengths"]]
            + ["Alerte : " + x for x in s["alerts"]]
            + ["À compléter : " + x for x in s["missing_information"]]
        )
        sections.append(part)
    sections.append(
        table_section(
            "Risque financier, indépendamment des garanties", report.get("financial_risk", {})
        )
    )
    sections.append(
        table_section(
            "Qualité documentaire, sans authentification", report.get("documentary_quality", {})
        )
    )
    sections += suggestions_sections(report.get("suggestions", []), True)
    sections.append(
        Section(title="Hypothèses et limites", paragraphs=report.get("assumptions", []))
    )
    sections.append(
        table_section(
            "Références des pièces, pages et coordonnées", report.get("sources", []), internal=True
        )
    )
    sections.append(table_section("Versions utilisées", report.get("versions", {})))
    return sections


def public_financial(report):
    # Données calculées autorisées uniquement ; pas de résumé libre comportant scores ou règles.
    fin = report.get("financial_calculations", {})
    allowed = {
        "period",
        "net_retained_income",
        "available_before_debt",
        "margin_after_credit",
        "margin_after_debt",
        "projected_reserve",
        "closing_cash",
        "operating_receipts",
        "cash_available_for_debt",
    }
    return {
        "periods": [{k: v for k, v in p.items() if k in allowed} for p in fin.get("periods", [])]
    }


def build_presentation(
    case,
    core,
    request,
    metadata,
    documents,
    report=None,
    publication=None,
    parent=None,
    simulation=None,
    validations=None,
):
    if request.template_id not in CATALOG[core]:
        raise ValueError("Modèle non applicable à ce noyau")
    internal = request.audience == "analyst"
    original = case
    evidence = {e["id"]: e for e in original.get("evidence", [])}
    case = case if internal else public_case(case)
    missing = list(case.get("missing_information", []))
    if not case.get("record_details", {}).get("address"):
        missing.append("Adresse non renseignée")
    if not case.get("record_details", {}).get("telephone") and not case.get(
        "record_details", {}
    ).get("email"):
        missing.append("Coordonnée de contact non renseignée")
    if core == "businesses" and not case.get("record_details", {}).get("representatives"):
        missing.append("Représentant non renseigné")

    def unknown(node, path=""):
        if isinstance(node, dict):
            if node.get("state") == "unknown":
                missing.append("Valeur inconnue : " + path)
            for k, v in node.items():
                if k != "internal_observations":
                    unknown(v, path + "." + label(k))
        elif isinstance(node, list):
            for i, v in enumerate(node, 1):
                unknown(v, path + f" {i}")

    unknown(case)
    if internal and report:
        missing += report.get("missing_information", [])
    elif report and report.get("missing_information"):
        missing.append(
            "Des informations nécessaires à l’analyse restent à confirmer avec l’analyste."
        )
    if request.template_id in ANALYSIS_TEMPLATES:
        sections = analysis_sections(
            report, request.template_id, internal, publication or {}, parent, simulation
        )
        if not report:
            missing.append("Analyse non disponible")
        sections.insert(
            0,
            table_section(
                "Demande analysée",
                {
                    "name": case["name"],
                    "requested_loan": (
                        {
                            k: v
                            for k, v in case["requested_loan"].items()
                            if k in {"reference", "principal", "annual_nominal_rate"}
                        }
                        if request.template_id == "analysis_summary"
                        else case["requested_loan"]
                    ),
                },
                evidence,
            ),
        )
    else:
        sections = form_sections(case, core, request.template_id, documents, evidence, internal)
    if internal and validations:
        sections.append(
            table_section("Historique des transcriptions contrôlées", validations, internal=True)
        )
    if (
        internal
        and case.get("record_details", {}).get("internal_observations")
        and request.template_id in ANALYSIS_TEMPLATES
    ):
        sections.append(
            Section(
                title="Observations internes",
                paragraphs=[case["record_details"]["internal_observations"]],
            )
        )
    status = "Brouillon — données à compléter" if missing else "Édition déclarative"
    if request.template_id in ANALYSIS_TEMPLATES:
        status = (
            "Analyse incomplète"
            if missing or not report or "sections" not in report
            else "Analyse disponible — sans décision de prêt"
        )
    notices = [
        "Document généré à partir des informations disponibles ; ne constitue pas un accord de crédit.",
        "Les déclarations ne sont ni des états financiers certifiés ni des documents émis par une banque.",
        "Une transcription contrôlée ne certifie pas l’authenticité du document source.",
    ]
    if report and (
        report.get("scoring", {}).get("criteria_validation_status") == "illustrative_not_validated"
        or (report.get("policy_snapshot") or {}).get("validation_status")
        == "illustrative_not_validated"
    ):
        notices.insert(
            0,
            "ILLUSTRATIF — NON VALIDÉ : politique de démonstration, aucun usage décisionnel réel.",
        )
    if missing:
        # Les demandes internes ne sont pas recopiées dans le modèle demandeur.
        sections.append(Section(title="Éléments à compléter", paragraphs=sorted(set(missing))))
    return Presentation(
        template_id=request.template_id,
        title=CATALOG[core][request.template_id],
        audience=request.audience,
        status=status,
        metadata=metadata,
        missing_information=sorted(set(missing)),
        notices=notices,
        sections=sections,
        signatures=request.template_id not in ANALYSIS_TEMPLATES,
    )
