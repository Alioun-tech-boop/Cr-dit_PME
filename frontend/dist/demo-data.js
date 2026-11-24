/* Extraits compacts de rapports v2 générés depuis les exemples synthétiques du dépôt. */
window.CREDIT_DEMO_DATA = {
  "version": "1.0.0",
  "notice": "Données synthétiques pré-calculées par financial_analysis_v2 ; politiques illustratives non approuvées ; aucune décision de crédit.",
  "cases": {
    "individual": {
      "id": "individual",
      "core": "individuals",
      "title": "Particulier salarié",
      "subtitle": "Capacité de remboursement et résistance à une baisse de revenus",
      "source_case": "examples/assessments/individual_control.json",
      "source_report": "examples/financial_v2/individual_control.report.json",
      "profile": "Salarié",
      "name": "Cas de contrôle synthétique 500000 / 300000 / 50000 / 80000",
      "activity": null,
      "as_of": "2026-01-31",
      "requested_loan": "240000",
      "justified_need": "240000",
      "opening_cash": null,
      "reserve": "1000000",
      "income_history": [
        {
          "period": "2025-11-01",
          "value": "500000"
        },
        {
          "period": "2025-12-01",
          "value": "500000"
        },
        {
          "period": "2026-01-01",
          "value": "500000"
        }
      ],
      "accounting": [],
      "inputs": [
        {
          "period": "2026-02-01",
          "income": "500000",
          "essential_expenses": "300000"
        },
        {
          "period": "2026-03-01",
          "income": "500000",
          "essential_expenses": "300000"
        },
        {
          "period": "2026-04-01",
          "income": "500000",
          "essential_expenses": "300000"
        },
        {
          "period": "2026-05-01",
          "income": "500000",
          "essential_expenses": "300000"
        },
        {
          "period": "2026-06-01",
          "income": "500000",
          "essential_expenses": "300000"
        },
        {
          "period": "2026-07-01",
          "income": "500000",
          "essential_expenses": "300000"
        }
      ],
      "periods": [
        {
          "period": "2026-02-01",
          "primary": "500000.00",
          "available": "200000.00",
          "existing_debt": "50000.00",
          "new_debt": "80000.00",
          "margin": "70000.00",
          "balance": "1070000.00",
          "ratio": "0.26"
        },
        {
          "period": "2026-03-01",
          "primary": "500000.00",
          "available": "200000.00",
          "existing_debt": "50000.00",
          "new_debt": "80000.00",
          "margin": "70000.00",
          "balance": "1140000.00",
          "ratio": "0.26"
        },
        {
          "period": "2026-04-01",
          "primary": "500000.00",
          "available": "200000.00",
          "existing_debt": "50000.00",
          "new_debt": "80000.00",
          "margin": "70000.00",
          "balance": "1210000.00",
          "ratio": "0.26"
        },
        {
          "period": "2026-05-01",
          "primary": "500000.00",
          "available": "200000.00",
          "existing_debt": "0",
          "new_debt": "0",
          "margin": "200000.00",
          "balance": "1410000.00",
          "ratio": "0E+2"
        },
        {
          "period": "2026-06-01",
          "primary": "500000.00",
          "available": "200000.00",
          "existing_debt": "0",
          "new_debt": "0",
          "margin": "200000.00",
          "balance": "1610000.00",
          "ratio": "0E+2"
        },
        {
          "period": "2026-07-01",
          "primary": "500000.00",
          "available": "200000.00",
          "existing_debt": "0",
          "new_debt": "0",
          "margin": "200000.00",
          "balance": "1810000.00",
          "ratio": "0E+2"
        }
      ],
      "summary": "Analyse financière déterministe des flux fournis. Aucun déficit identifié dans les seuls flux de base recensés. Dossier à compléter. Qualification selon politique individuals-illustrative-v2 (illustrative_not_validated). Ce rapport ne constitue pas un accord de crédit.",
      "operating_state": "dossier_a_completer",
      "minimum_margin": "70000.00",
      "minimum_balance": "1070000.00",
      "deficits": [],
      "scoring": {
        "criteria_score": null,
        "qualification": "favorable",
        "model_status": "disabled_by_design",
        "policy_status": "illustrative_not_validated",
        "mandatory_review": false
      },
      "documentary_quality": {
        "evidence_statuses": {
          "synthetic": "declared"
        },
        "amounts_without_evidence": [],
        "note": "Qualité documentaire distincte de la situation financière ; aucun taux de confiance.",
        "status": "favorable",
        "authenticity_status": "not_assessed",
        "coverage": {
          "important_amounts": 65,
          "usable_amounts": 65,
          "controlled_amounts": 0,
          "unknown_amounts": 0,
          "definition": "Comptage des montants fournis et admis par les validations existantes, pas une confiance prédictive."
        }
      },
      "sections": [
        {
          "title": "Identité, ménage et qualité documentaire",
          "status": "favorable"
        },
        {
          "title": "Revenus et stabilité",
          "status": "vigilance"
        },
        {
          "title": "Dépenses essentielles et budget du ménage",
          "status": "favorable"
        },
        {
          "title": "Dettes et comportement de remboursement",
          "status": "favorable"
        },
        {
          "title": "Capacité de remboursement",
          "status": "favorable"
        },
        {
          "title": "Épargne et réserve mobilisable",
          "status": "favorable"
        },
        {
          "title": "Cohérence du financement",
          "status": "favorable"
        },
        {
          "title": "Historique, régularité et tendances",
          "status": "favorable"
        },
        {
          "title": "Résistance aux difficultés",
          "status": "defavorable"
        }
      ],
      "missing_information": [
        "Dates complètes des flux et des échéances, rapprochées des totaux de période"
      ],
      "alerts": [
        "2026-02-01 : dépendance à une seule source déclarée ; continuité à documenter.",
        "2026-03-01 : dépendance à une seule source déclarée ; continuité à documenter.",
        "2026-04-01 : dépendance à une seule source déclarée ; continuité à documenter.",
        "2026-05-01 : dépendance à une seule source déclarée ; continuité à documenter.",
        "2026-06-01 : dépendance à une seule source déclarée ; continuité à documenter.",
        "2026-07-01 : dépendance à une seule source déclarée ; continuité à documenter.",
        "Baisse hypothétique des flux de 20 % : marge déficitaire sous ces hypothèses."
      ],
      "stress": [
        {
          "name": "Baisse hypothétique des flux de 20 %",
          "before": "70000.00",
          "after": "-30000.00",
          "balance_before": "1070000.00",
          "balance_after": "910000.00"
        }
      ],
      "reverse_tests": [
        {
          "parameter": "revenue_drop",
          "status": "found",
          "threshold": "0.140000152587890625",
          "notice": "Seuil dans cet intervalle et sous ces hypothèses seulement ; aucune probabilité de défaut."
        },
        {
          "parameter": "additional_instalment",
          "status": "found",
          "threshold": "70000.00000029103830456733715",
          "notice": "Seuil dans cet intervalle et sous ces hypothèses seulement ; aucune probabilité de défaut."
        }
      ],
      "variants": [
        {
          "months": 3,
          "principal": "240000",
          "compatible": true,
          "status": "evaluated",
          "total_repayment": "244815.92",
          "cost": "4815.92",
          "minimum_margin_after": "68394.69",
          "minimum_balance_after": "1068394.69",
          "information_requested": []
        },
        {
          "months": 6,
          "principal": "240000",
          "compatible": true,
          "status": "evaluated",
          "total_repayment": "248469.65",
          "cost": "8469.65",
          "minimum_margin_after": "108588.39",
          "minimum_balance_after": "1108588.39",
          "information_requested": []
        }
      ],
      "decision": null
    },
    "business": {
      "id": "business",
      "core": "businesses",
      "title": "PME de commerce",
      "subtitle": "Rentabilité, cycle d’exploitation et tension de trésorerie",
      "source_case": "examples/assessments/business_profitable_cash_tension.json",
      "source_report": "examples/financial_v2/business_profitable_cash_tension.report.json",
      "profile": "Entreprise · comptabilité structurée",
      "name": "Entreprise synthétique rentable, mais sous tension de trésorerie",
      "activity": "Commerce fictif",
      "as_of": "2026-01-31",
      "requested_loan": "60000",
      "justified_need": "60000",
      "opening_cash": "10000",
      "reserve": null,
      "income_history": [],
      "accounting": [
        {
          "period": "2025-10-01",
          "turnover": "800000",
          "operating_expenses": "200000",
          "net_result": "200000"
        },
        {
          "period": "2025-12-01",
          "turnover": "1000000",
          "operating_expenses": "250000",
          "net_result": "250000"
        }
      ],
      "inputs": [
        {
          "period": "2026-02-01",
          "receipts": "100000",
          "operating_expenses": "200000",
          "taxes": "10000",
          "household_withdrawals": "20000"
        },
        {
          "period": "2026-03-01",
          "receipts": "500000",
          "operating_expenses": "200000",
          "taxes": "10000",
          "household_withdrawals": "20000"
        },
        {
          "period": "2026-04-01",
          "receipts": "500000",
          "operating_expenses": "200000",
          "taxes": "10000",
          "household_withdrawals": "20000"
        }
      ],
      "periods": [
        {
          "period": "2026-02-01",
          "primary": "100000.00",
          "available": "-130000.00",
          "existing_debt": "11000",
          "new_debt": "22000",
          "margin": "-163000.00",
          "balance": "-153000.00",
          "ratio": "-3.939393939393939393939393939"
        },
        {
          "period": "2026-03-01",
          "primary": "500000.00",
          "available": "270000.00",
          "existing_debt": "21000",
          "new_debt": "0",
          "margin": "249000.00",
          "balance": "96000.00",
          "ratio": "12.85714285714285714285714286"
        },
        {
          "period": "2026-04-01",
          "primary": "500000.00",
          "available": "270000.00",
          "existing_debt": "0",
          "new_debt": "42000",
          "margin": "228000.00",
          "balance": "324000.00",
          "ratio": "6.428571428571428571428571429"
        }
      ],
      "summary": "Analyse financière déterministe des flux fournis. Des déficits ou limites imposent une revue approfondie. Dossier à compléter. Qualification selon politique businesses-illustrative-v2 (illustrative_not_validated). Ce rapport ne constitue pas un accord de crédit.",
      "operating_state": "revue_approfondie_requise",
      "minimum_margin": "-163000.00",
      "minimum_balance": "-153000.00",
      "deficits": [
        "2026-02-01"
      ],
      "scoring": {
        "criteria_score": null,
        "qualification": "defavorable",
        "model_status": "disabled_by_design",
        "policy_status": "illustrative_not_validated",
        "mandatory_review": true
      },
      "documentary_quality": {
        "evidence_statuses": {
          "synthetic": "declared"
        },
        "amounts_without_evidence": [],
        "note": "Qualité documentaire distincte de la situation financière ; aucun taux de confiance.",
        "status": "favorable",
        "authenticity_status": "not_assessed",
        "coverage": {
          "important_amounts": 99,
          "usable_amounts": 99,
          "controlled_amounts": 0,
          "unknown_amounts": 0,
          "definition": "Comptage des montants fournis et admis par les validations existantes, pas une confiance prédictive."
        }
      },
      "sections": [
        {
          "title": "Identité juridique et qualité documentaire",
          "status": "favorable"
        },
        {
          "title": "Activité et modèle économique",
          "status": "favorable"
        },
        {
          "title": "Rentabilité",
          "status": "favorable"
        },
        {
          "title": "Cycle d’exploitation et besoin en fonds de roulement",
          "status": "vigilance"
        },
        {
          "title": "Trésorerie",
          "status": "defavorable"
        },
        {
          "title": "Endettement et structure financière",
          "status": "favorable"
        },
        {
          "title": "Capacité de remboursement",
          "status": "defavorable"
        },
        {
          "title": "Projet financé et résistance aux chocs",
          "status": "incomplet"
        },
        {
          "title": "Garanties et recouvrement",
          "status": "favorable"
        },
        {
          "title": "Historique, régularité et tendances",
          "status": "favorable"
        },
        {
          "title": "Structure financière et liquidité",
          "status": "incomplet"
        },
        {
          "title": "Résistance aux difficultés",
          "status": "defavorable"
        }
      ],
      "missing_information": [
        "Dates complètes des flux et des échéances, rapprochées des totaux de période",
        "Postes de bilan comparables et unités pour fonds de roulement, trésorerie nette et liquidité.",
        "Traitement des taxes des soldes et dénominateurs à confirmer"
      ],
      "alerts": [
        "Retards de règlement : overdue_receivables",
        "Trésorerie projetée négative : tension de liquidité malgré une rentabilité éventuellement positive.",
        "Marge de remboursement déficitaire en 2026-02-01 ; revue obligatoire.",
        "Les recettes de projet sont prévisionnelles et nécessitent des hypothèses justifiées.",
        "Baisse hypothétique des flux de 20 % : marge déficitaire sous ces hypothèses."
      ],
      "stress": [
        {
          "name": "Baisse hypothétique des flux de 20 %",
          "before": "-163000.00",
          "after": "-183000.00",
          "balance_before": "-153000.00",
          "balance_after": "-173000.00"
        }
      ],
      "reverse_tests": [
        {
          "parameter": "revenue_drop",
          "status": "already_breached",
          "threshold": "0",
          "notice": "Seuil dans cet intervalle et sous ces hypothèses seulement ; aucune probabilité de défaut."
        },
        {
          "parameter": "additional_instalment",
          "status": "already_breached",
          "threshold": "0",
          "notice": "Seuil dans cet intervalle et sous ces hypothèses seulement ; aucune probabilité de défaut."
        }
      ],
      "variants": [
        {
          "months": 3,
          "principal": "240000",
          "compatible": false,
          "status": "evaluated",
          "total_repayment": "244815.92",
          "cost": "4815.92",
          "minimum_margin_after": "-222605.31",
          "minimum_balance_after": "-32605.31",
          "information_requested": []
        },
        {
          "months": 6,
          "principal": "240000",
          "compatible": false,
          "status": "needs_explicit_projections",
          "total_repayment": "248469.65",
          "cost": "8469.65",
          "information_requested": [
            "Flux explicites pour 2026-05-01, 2026-06-01, 2026-07-01"
          ]
        }
      ],
      "decision": null
    }
  }
};
