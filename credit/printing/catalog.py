"""Référentiel documentaire versionné, distinct des règles de crédit."""

SHARED = {
    "identification": "Fiche d’identification et de coordonnées",
    "credit_request": "Récapitulatif de demande de crédit",
    "debts": "Déclaration des dettes et engagements",
    "documents": "Pièces déposées et informations manquantes",
    "complete_file": "Dossier récapitulatif complet",
    "analysis_summary": "Synthèse de l’analyse",
    "analysis_report": "Rapport détaillé d’analyse",
    "simulation_report": "Rapport de simulation",
    "improvement_plan": "Plan d’amélioration proposé",
}
CATALOG = {
    "individuals": {
        **SHARED,
        "income_expenses": "Déclaration des revenus et charges",
        "household_budget": "Budget du ménage",
    },
    "businesses": {
        **SHARED,
        "identification": "Fiche d’identification de l’entreprise et des représentants",
        "credit_request": "Récapitulatif de demande de financement",
        "activity": "Présentation de l’activité",
        "financial_declaration": "Déclaration financière issue des champs saisis",
        "cashflows": "Tableau des encaissements et décaissements",
        "working_capital": "État des créances, fournisseurs et stocks",
        "project_budget": "Budget du projet et plan de financement",
    },
}
ANALYSIS_TEMPLATES = {
    "analysis_summary",
    "analysis_report",
    "simulation_report",
    "improvement_plan",
}


def templates(core):
    return [
        {
            "id": key,
            "title": title,
            "version": "print-1.0.0",
            "requires_assessment": key in ANALYSIS_TEMPLATES,
            "audiences": ["applicant", "analyst"],
        }
        for key, title in CATALOG[core].items()
    ]
