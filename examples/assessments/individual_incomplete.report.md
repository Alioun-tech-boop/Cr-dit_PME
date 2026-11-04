# Rapport Crédit PME
Analyse particulier : la capacité financière ne peut pas être complètement évaluée. 8 informations ou vérifications restent demandées. Score par critères indisponible ; les données et indicateurs restent consultables. Combinaison 70/30 indisponible. Aucune décision de prêt ni authenticité documentaire n’est déduite.

État opérationnel : revue_approfondie_requise
Version : section-analysis-1.0.0
Politique : individuals-illustrative-v1:1

## Risque financier
incomplete
Indice de risque = 100 − score de solvabilité ; ce n’est pas une probabilité de défaut.
Modèle : not_available

## Identité, ménage et qualité documentaire — favorable
Contrôle d’exploitabilité et de rattachement ; ne mesure ni la solvabilité financière ni l’authenticité des documents.
- evidence_count : 1 pièces. Formule : Nombre de références fournies.
- Source analysis_details.identity.subject_linked : synthetic.
- Source analysis_details.identity.household_confirmed : synthetic.
- Source analysis_details.identity.representation_confirmed : synthetic.
- Source analysis_details.identity.authorizations_applicable : synthetic.
- Source analysis_details.identity.authorizations_confirmed : synthetic.
- Source analysis_details.identity.evidence_ids.0 : synthetic.

## Revenus et stabilité — vigilance
Chiffre d’affaires et revenu personnel ne sont pas confondus. Les revenus par période restent distincts de leur stabilité ; aucune continuité future n’est garantie.
- net_by_source_total_2026-02-01 : 500000 XOF. Formule : Somme des revenus personnels nets par source, avant neutralisation globale des retenues.
- net_by_source_total_2026-03-01 : 500000 XOF. Formule : Somme des revenus personnels nets par source, avant neutralisation globale des retenues.
- net_by_source_total_2026-04-01 : 500000 XOF. Formule : Somme des revenus personnels nets par source, avant neutralisation globale des retenues.
- net_by_source_total_2026-05-01 : 500000 XOF. Formule : Somme des revenus personnels nets par source, avant neutralisation globale des retenues.
- net_by_source_total_2026-06-01 : 500000 XOF. Formule : Somme des revenus personnels nets par source, avant neutralisation globale des retenues.
- net_by_source_total_2026-07-01 : 500000 XOF. Formule : Somme des revenus personnels nets par source, avant neutralisation globale des retenues.
- retained_net_2026-02-01 : 500000.00 XOF. Formule : Nets retenus après neutralisation des retenues et hypothèses explicites du scénario.
- retained_net_2026-03-01 : 500000.00 XOF. Formule : Nets retenus après neutralisation des retenues et hypothèses explicites du scénario.
- retained_net_2026-04-01 : 500000.00 XOF. Formule : Nets retenus après neutralisation des retenues et hypothèses explicites du scénario.
- retained_net_2026-05-01 : 500000.00 XOF. Formule : Nets retenus après neutralisation des retenues et hypothèses explicites du scénario.
- retained_net_2026-06-01 : 500000.00 XOF. Formule : Nets retenus après neutralisation des retenues et hypothèses explicites du scénario.
- retained_net_2026-07-01 : 500000.00 XOF. Formule : Nets retenus après neutralisation des retenues et hypothèses explicites du scénario.
- history_cv : 0 ratio. Formule : Écart type de population / moyenne sur au moins trois revenus historiques comparables, moyenne > 0.
- largest_source_share : 1 ratio. Formule : Maximum du poids d’une source dans les revenus nets déclarés de chaque période.
- Alerte : 2026-02-01 : dépendance à une seule source déclarée ; continuité à documenter.
- Alerte : 2026-03-01 : dépendance à une seule source déclarée ; continuité à documenter.
- Alerte : 2026-04-01 : dépendance à une seule source déclarée ; continuité à documenter.
- Alerte : 2026-05-01 : dépendance à une seule source déclarée ; continuité à documenter.
- Alerte : 2026-06-01 : dépendance à une seule source déclarée ; continuité à documenter.
- Alerte : 2026-07-01 : dépendance à une seule source déclarée ; continuité à documenter.
- Source periods.0.incomes.0.net : synthetic.
- Source periods.0.essential_expenses : synthetic.
- Source periods.0.payroll_loan_deductions : synthetic.
- Source periods.1.incomes.0.net : synthetic.
- Source periods.1.essential_expenses : synthetic.
- Source periods.1.payroll_loan_deductions : synthetic.
- Source periods.2.incomes.0.net : synthetic.
- Source periods.2.essential_expenses : synthetic.
- Source periods.2.payroll_loan_deductions : synthetic.
- Source periods.3.incomes.0.net : synthetic.
- Source periods.3.essential_expenses : synthetic.
- Source periods.3.payroll_loan_deductions : synthetic.
- Source periods.4.incomes.0.net : synthetic.
- Source periods.4.essential_expenses : synthetic.
- Source periods.4.payroll_loan_deductions : synthetic.
- Source periods.5.incomes.0.net : synthetic.
- Source periods.5.essential_expenses : synthetic.
- Source periods.5.payroll_loan_deductions : synthetic.
- Source income_history.0.net_personal_income : synthetic.
- Source income_history.1.net_personal_income : synthetic.
- Source income_history.2.net_personal_income : synthetic.
- Source analysis_details.continuity.0.text : synthetic.
- Source analysis_details.continuity.0.evidence_ids.0 : synthetic.

## Dépenses essentielles et budget du ménage — incomplet
Les dépenses connues à venir sont intégrées dans leur période lorsqu’elles sont explicitement hors total ; les postes déjà inclus ne sont pas déduits deux fois.
- essential_2026-02-01 : indisponible XOF. Formule : Total déclaré + dépenses nécessaires hors total, une seule fois.
- essential_2026-03-01 : 300000 XOF. Formule : Total déclaré + dépenses nécessaires hors total, une seule fois.
- essential_2026-04-01 : 300000 XOF. Formule : Total déclaré + dépenses nécessaires hors total, une seule fois.
- essential_2026-05-01 : 300000 XOF. Formule : Total déclaré + dépenses nécessaires hors total, une seule fois.
- essential_2026-06-01 : 300000 XOF. Formule : Total déclaré + dépenses nécessaires hors total, une seule fois.
- essential_2026-07-01 : 300000 XOF. Formule : Total déclaré + dépenses nécessaires hors total, une seule fois.
- retained_essential_2026-02-01 : indisponible XOF. Formule : Charges essentielles retenues dans le calcul, y compris coûts hors total et stress explicite.
- retained_essential_2026-03-01 : 300000.00 XOF. Formule : Charges essentielles retenues dans le calcul, y compris coûts hors total et stress explicite.
- retained_essential_2026-04-01 : 300000.00 XOF. Formule : Charges essentielles retenues dans le calcul, y compris coûts hors total et stress explicite.
- retained_essential_2026-05-01 : 300000.00 XOF. Formule : Charges essentielles retenues dans le calcul, y compris coûts hors total et stress explicite.
- retained_essential_2026-06-01 : 300000.00 XOF. Formule : Charges essentielles retenues dans le calcul, y compris coûts hors total et stress explicite.
- retained_essential_2026-07-01 : 300000.00 XOF. Formule : Charges essentielles retenues dans le calcul, y compris coûts hors total et stress explicite.
- À compléter : Rapprocher le détail et le total des dépenses essentielles en 2026-02-01
- À compléter : essential_expenses.2026-02-01 : valeur inconnue, contradictoire ou non validée
- Source analysis_details.expenses.0.amount : synthetic.
- Source analysis_details.expenses.1.amount : synthetic.
- Source analysis_details.expenses.2.amount : synthetic.
- Source analysis_details.expenses.3.amount : synthetic.
- Source analysis_details.expenses.4.amount : synthetic.
- Source analysis_details.expenses.5.amount : synthetic.
- Source analysis_details.expenses.6.amount : synthetic.
- Source analysis_details.expenses.7.amount : synthetic.
- Source analysis_details.expenses.8.amount : synthetic.
- Source analysis_details.expenses.9.amount : synthetic.
- Source analysis_details.expenses.10.amount : synthetic.
- Source analysis_details.expenses.11.amount : synthetic.
- Source analysis_details.expenses.12.amount : synthetic.
- Source analysis_details.expenses.13.amount : synthetic.
- Source analysis_details.expenses.14.amount : synthetic.
- Source analysis_details.expenses.15.amount : synthetic.
- Source analysis_details.expenses.16.amount : synthetic.
- Source analysis_details.expenses.17.amount : synthetic.
- Source periods.0.essential_expenses : synthetic.
- Source periods.1.essential_expenses : synthetic.
- Source periods.2.essential_expenses : synthetic.
- Source periods.3.essential_expenses : synthetic.
- Source periods.4.essential_expenses : synthetic.
- Source periods.5.essential_expenses : synthetic.

## Dettes et comportement de remboursement — favorable
Les échéanciers comprennent capital, intérêts et frais. Les retenues salariales sont réintégrées au revenu si elles ont déjà été déduites, puis les échéances sont retranchées une seule fois.
- existing_principal : 150000 XOF. Formule : Somme du capital restant à rembourser des échéanciers existants.
- arrears_0 : 0 XOF. Formule : Arriérés déclarés à la date indiquée.
- Source existing_loans.0.principal : synthetic.
- Source existing_loans.0.schedule.0.principal : synthetic.
- Source existing_loans.0.schedule.0.interest : synthetic.
- Source existing_loans.0.schedule.0.fees : synthetic.
- Source existing_loans.0.schedule.1.principal : synthetic.
- Source existing_loans.0.schedule.1.interest : synthetic.
- Source existing_loans.0.schedule.1.fees : synthetic.
- Source existing_loans.0.schedule.2.principal : synthetic.
- Source existing_loans.0.schedule.2.interest : synthetic.
- Source existing_loans.0.schedule.2.fees : synthetic.
- Source analysis_details.repayment_observations.0.arrears : synthetic.
- Source periods.0.payroll_loan_deductions : synthetic.
- Source periods.1.payroll_loan_deductions : synthetic.
- Source periods.2.payroll_loan_deductions : synthetic.
- Source periods.3.payroll_loan_deductions : synthetic.
- Source periods.4.payroll_loan_deductions : synthetic.
- Source periods.5.payroll_loan_deductions : synthetic.

## Capacité de remboursement — incomplet
Chaque période est examinée. Un total annuel favorable ne masque pas un déficit mensuel. Les projections sont des hypothèses, pas des recettes certaines.
- available_2026-02-01 : indisponible XOF. Formule : Revenus nets retenus − dépenses essentielles.
- margin_2026-02-01 : indisponible XOF. Formule : Disponible avant dette − service dette existante − service nouvelle dette.
- debt_weight_2026-02-01 : 0.26 ratio. Formule : Service total / revenus retenus, si revenus > 0.
- available_2026-03-01 : 200000.00 XOF. Formule : Revenus nets retenus − dépenses essentielles.
- margin_2026-03-01 : 70000.00 XOF. Formule : Disponible avant dette − service dette existante − service nouvelle dette.
- debt_weight_2026-03-01 : 0.26 ratio. Formule : Service total / revenus retenus, si revenus > 0.
- available_2026-04-01 : 200000.00 XOF. Formule : Revenus nets retenus − dépenses essentielles.
- margin_2026-04-01 : 70000.00 XOF. Formule : Disponible avant dette − service dette existante − service nouvelle dette.
- debt_weight_2026-04-01 : 0.26 ratio. Formule : Service total / revenus retenus, si revenus > 0.
- available_2026-05-01 : 200000.00 XOF. Formule : Revenus nets retenus − dépenses essentielles.
- margin_2026-05-01 : 200000.00 XOF. Formule : Disponible avant dette − service dette existante − service nouvelle dette.
- debt_weight_2026-05-01 : 0E+2 ratio. Formule : Service total / revenus retenus, si revenus > 0.
- available_2026-06-01 : 200000.00 XOF. Formule : Revenus nets retenus − dépenses essentielles.
- margin_2026-06-01 : 200000.00 XOF. Formule : Disponible avant dette − service dette existante − service nouvelle dette.
- debt_weight_2026-06-01 : 0E+2 ratio. Formule : Service total / revenus retenus, si revenus > 0.
- available_2026-07-01 : 200000.00 XOF. Formule : Revenus nets retenus − dépenses essentielles.
- margin_2026-07-01 : 200000.00 XOF. Formule : Disponible avant dette − service dette existante − service nouvelle dette.
- debt_weight_2026-07-01 : 0E+2 ratio. Formule : Service total / revenus retenus, si revenus > 0.
- minimum_margin_income : 0.14000000 ratio. Formule : Minimum des ratios par période calculables ; les périodes sans dette sont exclues de la couverture.
- À compléter : Flux et services de dette à compléter en 2026-02-01
- À compléter : dépenses essentielles/2026-02-01
- À compléter : réserve mobilisable
- Source periods.0.incomes.0.net : synthetic.
- Source periods.0.essential_expenses : synthetic.
- Source periods.0.payroll_loan_deductions : synthetic.
- Source periods.1.incomes.0.net : synthetic.
- Source periods.1.essential_expenses : synthetic.
- Source periods.1.payroll_loan_deductions : synthetic.
- Source periods.2.incomes.0.net : synthetic.
- Source periods.2.essential_expenses : synthetic.
- Source periods.2.payroll_loan_deductions : synthetic.
- Source periods.3.incomes.0.net : synthetic.
- Source periods.3.essential_expenses : synthetic.
- Source periods.3.payroll_loan_deductions : synthetic.
- Source periods.4.incomes.0.net : synthetic.
- Source periods.4.essential_expenses : synthetic.
- Source periods.4.payroll_loan_deductions : synthetic.
- Source periods.5.incomes.0.net : synthetic.
- Source periods.5.essential_expenses : synthetic.
- Source periods.5.payroll_loan_deductions : synthetic.
- Source existing_loans.0.principal : synthetic.
- Source existing_loans.0.schedule.0.principal : synthetic.
- Source existing_loans.0.schedule.0.interest : synthetic.
- Source existing_loans.0.schedule.0.fees : synthetic.
- Source existing_loans.0.schedule.1.principal : synthetic.
- Source existing_loans.0.schedule.1.interest : synthetic.
- Source existing_loans.0.schedule.1.fees : synthetic.
- Source existing_loans.0.schedule.2.principal : synthetic.
- Source existing_loans.0.schedule.2.interest : synthetic.
- Source existing_loans.0.schedule.2.fees : synthetic.
- Source requested_loan.principal : synthetic.
- Source requested_loan.schedule.0.principal : synthetic.
- Source requested_loan.schedule.0.interest : synthetic.
- Source requested_loan.schedule.0.fees : synthetic.
- Source requested_loan.schedule.1.principal : synthetic.
- Source requested_loan.schedule.1.interest : synthetic.
- Source requested_loan.schedule.1.fees : synthetic.
- Source requested_loan.schedule.2.principal : synthetic.
- Source requested_loan.schedule.2.interest : synthetic.
- Source requested_loan.schedule.2.fees : synthetic.

## Réserve et résistance aux difficultés — incomplet
L’épargne bloquée est présentée séparément et exclue du disponible. La réserve ponctuelle peut couvrir une tension temporaire, jamais remplacer durablement un revenu.
- reserve_months : indisponible périodes de dépenses essentielles. Formule : Réserve mobilisable initiale / dépenses essentielles maximales d’une période ; pas un revenu.
- minimum_reserve : indisponible XOF. Formule : Minimum des réserves projetées de fin de période.
- stress_reserve_0 : indisponible XOF. Formule : Réserve minimale recalculée sous les hypothèses du scénario Illustration non validée : revenu/ventes −20 %.
- stress_margin_0 : indisponible XOF. Formule : Marge minimale sous le scénario Illustration non validée : revenu/ventes −20 %.
- stress_reserve_1 : indisponible XOF. Formule : Réserve minimale recalculée sous les hypothèses du scénario Illustration non validée : charges +10 %.
- stress_margin_1 : indisponible XOF. Formule : Marge minimale sous le scénario Illustration non validée : charges +10 %.
- Alerte : Marge déficitaire sous Illustration non validée : revenu/ventes −20 % ; réserve ponctuelle et continuité à vérifier.
- À compléter : Réserve mobilisable et flux de toutes les périodes nécessaires à la projection
- À compléter : mobilizable_reserve : valeur inconnue, contradictoire ou non validée
- Source mobilizable_reserve : synthetic.
- Source analysis_details.blocked_savings : synthetic.

## Cohérence du financement — favorable
Besoin, apport et coûts sont présentés séparément. Aucun emprunt artificiel d’apport ni baisse des dépenses essentielles n’est proposé.
- contribution_gap : 0 XOF. Formule : max(0, apport nécessaire − apport vérifié) ; aucun apport supposé disponible.
- announced_contribution : 24000 XOF. Formule : Apport annoncé séparément de l’apport vérifié.
- required_contribution : 24000.00 XOF. Formule : max(besoin − crédit, minimum du produit lorsqu’une politique applicable le définit).
- total_repayment : 240000.00 XOF. Formule : Somme du capital, des intérêts et frais exigibles sur l’échéancier complet.
- total_credit_cost : 0.00 XOF. Formule : Total à rembourser − capital demandé.
- instalment_count : 3 échéances. Formule : Nombre d’échéances explicites ; ne suppose pas une durée mensuelle pour un crédit irrégulier.
- Source analysis_details.funding.justified_need : synthetic.
- Source analysis_details.funding.announced_contribution : synthetic.
- Source analysis_details.funding.verified_contribution : synthetic.
- Source analysis_details.funding.purpose.text : synthetic.
- Source analysis_details.funding.purpose.evidence_ids.0 : synthetic.
- Source requested_loan.principal : synthetic.
- Source requested_loan.schedule.0.principal : synthetic.
- Source requested_loan.schedule.0.interest : synthetic.
- Source requested_loan.schedule.0.fees : synthetic.
- Source requested_loan.schedule.1.principal : synthetic.
- Source requested_loan.schedule.1.interest : synthetic.
- Source requested_loan.schedule.1.fees : synthetic.
- Source requested_loan.schedule.2.principal : synthetic.
- Source requested_loan.schedule.2.interest : synthetic.
- Source requested_loan.schedule.2.fees : synthetic.

## Suggestions
- [haute] Compléter : Rapprocher le détail et le total des dépenses essentielles en 2026-02-01 ; essential_expenses.2026-02-01 : valeur inconnue, contradictoire ou non validée Destinataire : analyste.
  Limites : La collecte améliore l’exploitabilité, pas une probabilité de remboursement mesurée.
- [haute] Compléter : Flux et services de dette à compléter en 2026-02-01 ; dépenses essentielles/2026-02-01 ; réserve mobilisable Destinataire : analyste.
  Limites : La collecte améliore l’exploitabilité, pas une probabilité de remboursement mesurée.
- [haute] Compléter : Réserve mobilisable et flux de toutes les périodes nécessaires à la projection ; mobilizable_reserve : valeur inconnue, contradictoire ou non validée Destinataire : analyste.
  Limites : La collecte améliore l’exploitabilité, pas une probabilité de remboursement mesurée.

## Décision du prêteur
Non fournie. Ce rapport n’est pas un accord bancaire.
