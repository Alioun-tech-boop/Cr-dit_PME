# Rapport Crédit PME
Analyse financière déterministe des flux fournis. Des déficits ou limites imposent une revue approfondie. Dossier à compléter. Qualification selon politique businesses-illustrative-v2 (illustrative_not_validated). Ce rapport ne constitue pas un accord de crédit.

État opérationnel : revue_approfondie_requise
Version : financial_analysis_v2
Politique : businesses-illustrative-v2:2.0.0

## Risque financier
payment_pressure
Indice de risque = 100 − score de solvabilité ; ce n’est pas une probabilité de défaut.
Modèle : disabled_by_design

## Identité juridique et qualité documentaire — favorable
Contrôle d’exploitabilité et de rattachement ; ne mesure ni la solvabilité financière ni l’authenticité des documents.
- evidence_count : 1 pièces. Formule : Nombre de références fournies.
- Source analysis_details.identity.subject_linked : synthetic.
- Source analysis_details.identity.household_confirmed : synthetic.
- Source analysis_details.identity.representation_confirmed : synthetic.
- Source analysis_details.identity.authorizations_applicable : synthetic.
- Source analysis_details.identity.authorizations_confirmed : synthetic.
- Source analysis_details.identity.evidence_ids.0 : synthetic.

## Activité et modèle économique — favorable
Commandes, factures et encaissements réels sont identifiés séparément. Seuls les encaissements contribuent à la trésorerie du noyau direct.
- retained_receipts_2026-02-01 : 50000.00 XOF. Formule : Encaissements retenus après hypothèses explicites ; commandes et factures exclues.
- retained_receipts_2026-03-01 : 700000.00 XOF. Formule : Encaissements retenus après hypothèses explicites ; commandes et factures exclues.
- retained_receipts_2026-04-01 : 300000.00 XOF. Formule : Encaissements retenus après hypothèses explicites ; commandes et factures exclues.
- largest_customer_share : 0.80000000 ratio. Formule : Maximum des encaissements d’un client / encaissements totaux rapprochés ; commandes et factures exclues.
- receipts_history_cv : 0.72008230 ratio. Formule : Variabilité des encaissements historiques ; ne prouve pas à elle seule une saisonnalité annuelle.
- Source analysis_details.counterparties.0.amount : synthetic.
- Source analysis_details.counterparties.1.amount : synthetic.
- Source analysis_details.counterparties.2.amount : synthetic.
- Source analysis_details.counterparties.3.amount : synthetic.
- Source analysis_details.counterparties.4.amount : synthetic.
- Source analysis_details.counterparties.5.amount : synthetic.
- Source historical_cashflows.0.receipts : synthetic.
- Source historical_cashflows.0.operating_expenses : synthetic.
- Source historical_cashflows.0.taxes : synthetic.
- Source historical_cashflows.0.essential_investments : synthetic.
- Source historical_cashflows.0.household_withdrawals : synthetic.
- Source historical_cashflows.0.requested_loan_disbursement : synthetic.
- Source historical_cashflows.0.financed_uses : synthetic.
- Source historical_cashflows.1.receipts : synthetic.
- Source historical_cashflows.1.operating_expenses : synthetic.
- Source historical_cashflows.1.taxes : synthetic.
- Source historical_cashflows.1.essential_investments : synthetic.
- Source historical_cashflows.1.household_withdrawals : synthetic.
- Source historical_cashflows.1.requested_loan_disbursement : synthetic.
- Source historical_cashflows.1.financed_uses : synthetic.
- Source historical_cashflows.2.receipts : synthetic.
- Source historical_cashflows.2.operating_expenses : synthetic.
- Source historical_cashflows.2.taxes : synthetic.
- Source historical_cashflows.2.essential_investments : synthetic.
- Source historical_cashflows.2.household_withdrawals : synthetic.
- Source historical_cashflows.2.requested_loan_disbursement : synthetic.
- Source historical_cashflows.2.financed_uses : synthetic.
- Source analysis_details.dependencies.0.text : synthetic.
- Source analysis_details.dependencies.0.evidence_ids.0 : synthetic.
- Source analysis_details.seasonality.text : synthetic.
- Source analysis_details.seasonality.evidence_ids.0 : synthetic.

## Rentabilité — favorable
Les pertes et résultats sont signés. Les unités sont converties explicitement ; une unité inconnue bloque le calcul, sans supposer des francs ou des milliers.
- turnover_0 : 800000 XOF. Formule : Chiffre d’affaires × multiplicateur d’unité explicitement fourni.
- gross_margin_0 : 0.50000000 ratio. Formule : (Chiffre d’affaires − coût des ventes) / chiffre d’affaires.
- operating_result_0 : 200000 XOF. Formule : CA − coûts des ventes − charges hors coût des ventes ; ou CA − charges incluant déjà ces coûts.
- net_result_0 : 200000 XOF. Formule : Résultat net comptable fourni et rapproché, pas une déduction des seuls flux de caisse.
- net_margin_0 : 0.25000000 ratio. Formule : Résultat net / chiffre d’affaires strictement positif.
- turnover_1 : 1000000 XOF. Formule : Chiffre d’affaires × multiplicateur d’unité explicitement fourni.
- gross_margin_1 : 0.50000000 ratio. Formule : (Chiffre d’affaires − coût des ventes) / chiffre d’affaires.
- operating_result_1 : 250000 XOF. Formule : CA − coûts des ventes − charges hors coût des ventes ; ou CA − charges incluant déjà ces coûts.
- net_result_1 : 250000 XOF. Formule : Résultat net comptable fourni et rapproché, pas une déduction des seuls flux de caisse.
- net_margin_1 : 0.25000000 ratio. Formule : Résultat net / chiffre d’affaires strictement positif.
- turnover_growth : 0.25000000 ratio. Formule : (CA comparable après − CA comparable avant) / CA avant ; normalisation journalière seulement si explicitement demandée.
- net_margin : 0.25000000 ratio. Formule : Dernière marge nette comptable calculable, sans comparaison implicite de durées.
- Source analysis_details.accounting.0.turnover : synthetic.
- Source analysis_details.accounting.0.operating_expenses : synthetic.
- Source analysis_details.accounting.0.cost_of_sales : synthetic.
- Source analysis_details.accounting.0.operating_result : synthetic.
- Source analysis_details.accounting.0.net_result : synthetic.
- Source analysis_details.accounting.0.equity : synthetic.
- Source analysis_details.accounting.0.total_debt : synthetic.
- Source analysis_details.accounting.1.turnover : synthetic.
- Source analysis_details.accounting.1.operating_expenses : synthetic.
- Source analysis_details.accounting.1.cost_of_sales : synthetic.
- Source analysis_details.accounting.1.operating_result : synthetic.
- Source analysis_details.accounting.1.net_result : synthetic.
- Source analysis_details.accounting.1.equity : synthetic.
- Source analysis_details.accounting.1.total_debt : synthetic.

## Cycle d’exploitation et besoin en fonds de roulement — vigilance
Les délais ne sont pas fabriqués à partir de soldes seuls. L’analyse BFR est informative : aucune seconde déduction dans la trésorerie directe.
- working_capital : 680000 XOF. Formule : Stocks + créances clients − dettes fournisseurs, à la même date.
- dso : indisponible jours. Formule : average_receivables / credit_sales × jours de la période ; moyennes obligatoires.
- dpo : indisponible jours. Formule : average_payables / credit_purchases × jours de la période ; moyennes obligatoires.
- dio : indisponible jours. Formule : average_inventory / cost_of_sales × jours de la période ; moyennes obligatoires.
- overdue_receivables : 200000 XOF. Formule : Montants échus non réglés explicitement fournis.
- overdue_payables : 0 XOF. Formule : Montants échus non réglés explicitement fournis.
- Alerte : Retards de règlement : overdue_receivables
- À compléter : Traitement des taxes des soldes et dénominateurs à confirmer
- À compléter : Traitement des taxes des soldes et dénominateurs à confirmer
- À compléter : Traitement des taxes des soldes et dénominateurs à confirmer
- Source analysis_details.working_capital.inventory : synthetic.
- Source analysis_details.working_capital.receivables : synthetic.
- Source analysis_details.working_capital.payables : synthetic.
- Source analysis_details.working_capital.average_inventory : synthetic.
- Source analysis_details.working_capital.average_receivables : synthetic.
- Source analysis_details.working_capital.average_payables : synthetic.
- Source analysis_details.working_capital.credit_sales : synthetic.
- Source analysis_details.working_capital.credit_purchases : synthetic.
- Source analysis_details.working_capital.cost_of_sales : synthetic.
- Source analysis_details.working_capital.overdue_receivables : synthetic.
- Source analysis_details.working_capital.overdue_payables : synthetic.

## Trésorerie — defavorable
Encaissements d’exploitation, nouveaux financements et emplois des fonds sont séparés. Les prélèvements du ménage déjà inclus dans l’exploitation ne sont pas déduits une seconde fois.
- closing_cash_2026-02-01 : -203000.00 XOF. Formule : Trésorerie début + marge après dette + crédit reçu − emplois financés.
- closing_cash_2026-03-01 : 246000.00 XOF. Formule : Trésorerie début + marge après dette + crédit reçu − emplois financés.
- closing_cash_2026-04-01 : 274000.00 XOF. Formule : Trésorerie début + marge après dette + crédit reçu − emplois financés.
- minimum_cash : -203000.00 XOF. Formule : Minimum des soldes de fin de période ; date conservée dans les calculs financiers.
- Alerte : Trésorerie projetée négative : tension de liquidité malgré une rentabilité éventuellement positive.
- Source opening_cash : synthetic.
- Source periods.0.receipts : synthetic.
- Source periods.0.operating_expenses : synthetic.
- Source periods.0.taxes : synthetic.
- Source periods.0.essential_investments : synthetic.
- Source periods.0.household_withdrawals : synthetic.
- Source periods.0.requested_loan_disbursement : synthetic.
- Source periods.0.financed_uses : synthetic.
- Source periods.1.receipts : synthetic.
- Source periods.1.operating_expenses : synthetic.
- Source periods.1.taxes : synthetic.
- Source periods.1.essential_investments : synthetic.
- Source periods.1.household_withdrawals : synthetic.
- Source periods.1.requested_loan_disbursement : synthetic.
- Source periods.1.financed_uses : synthetic.
- Source periods.2.receipts : synthetic.
- Source periods.2.operating_expenses : synthetic.
- Source periods.2.taxes : synthetic.
- Source periods.2.essential_investments : synthetic.
- Source periods.2.household_withdrawals : synthetic.
- Source periods.2.requested_loan_disbursement : synthetic.
- Source periods.2.financed_uses : synthetic.

## Endettement et structure financière — favorable
Les échéanciers comprennent capital, intérêts et frais. Les retenues salariales sont réintégrées au revenu si elles ont déjà été déduites, puis les échéances sont retranchées une seule fois.
- existing_principal : 30000 XOF. Formule : Somme du capital restant à rembourser des échéanciers existants.
- arrears_0 : 0 XOF. Formule : Arriérés déclarés à la date indiquée.
- equity : 300000 XOF. Formule : Valeur structurée à la date de référence.
- off_balance_commitments : 0 XOF. Formule : Valeur structurée à la date de référence.
- tax_arrears : 0 XOF. Formule : Valeur structurée à la date de référence.
- social_arrears : 0 XOF. Formule : Valeur structurée à la date de référence.
- debt_equity : 0.10000000 ratio. Formule : Capital existant / fonds propres, seulement si fonds propres > 0.
- Source existing_loans.0.principal : synthetic.
- Source existing_loans.0.schedule.0.principal : synthetic.
- Source existing_loans.0.schedule.0.interest : synthetic.
- Source existing_loans.0.schedule.0.fees : synthetic.
- Source existing_loans.0.schedule.1.principal : synthetic.
- Source existing_loans.0.schedule.1.interest : synthetic.
- Source existing_loans.0.schedule.1.fees : synthetic.
- Source analysis_details.repayment_observations.0.arrears : synthetic.
- Source analysis_details.equity : synthetic.
- Source analysis_details.off_balance_commitments : synthetic.
- Source analysis_details.tax_arrears : synthetic.
- Source analysis_details.social_arrears : synthetic.

## Capacité de remboursement — defavorable
Chaque période est examinée. Un total annuel favorable ne masque pas un déficit mensuel. Les projections sont des hypothèses, pas des recettes certaines.
- available_2026-02-01 : -180000.00 XOF. Formule : Encaissements − sorties nécessaires hors dette.
- margin_2026-02-01 : -213000.00 XOF. Formule : Disponible avant dette − service dette existante − service nouvelle dette.
- coverage_2026-02-01 : -5.454545454545454545454545455 ratio. Formule : Disponible pour dette / service total, si service > 0.
- available_2026-03-01 : 470000.00 XOF. Formule : Encaissements − sorties nécessaires hors dette.
- margin_2026-03-01 : 449000.00 XOF. Formule : Disponible avant dette − service dette existante − service nouvelle dette.
- coverage_2026-03-01 : 22.38095238095238095238095238 ratio. Formule : Disponible pour dette / service total, si service > 0.
- available_2026-04-01 : 70000.00 XOF. Formule : Encaissements − sorties nécessaires hors dette.
- margin_2026-04-01 : 28000.00 XOF. Formule : Disponible avant dette − service dette existante − service nouvelle dette.
- coverage_2026-04-01 : 1.666666666666666666666666667 ratio. Formule : Disponible pour dette / service total, si service > 0.
- minimum_coverage : -5.454545454545454545454545455 ratio. Formule : Minimum des ratios par période calculables ; les périodes sans dette sont exclues de la couverture.
- Alerte : Marge de remboursement déficitaire en 2026-02-01 ; revue obligatoire.
- Source periods.0.receipts : synthetic.
- Source periods.0.operating_expenses : synthetic.
- Source periods.0.taxes : synthetic.
- Source periods.0.essential_investments : synthetic.
- Source periods.0.household_withdrawals : synthetic.
- Source periods.0.requested_loan_disbursement : synthetic.
- Source periods.0.financed_uses : synthetic.
- Source periods.1.receipts : synthetic.
- Source periods.1.operating_expenses : synthetic.
- Source periods.1.taxes : synthetic.
- Source periods.1.essential_investments : synthetic.
- Source periods.1.household_withdrawals : synthetic.
- Source periods.1.requested_loan_disbursement : synthetic.
- Source periods.1.financed_uses : synthetic.
- Source periods.2.receipts : synthetic.
- Source periods.2.operating_expenses : synthetic.
- Source periods.2.taxes : synthetic.
- Source periods.2.essential_investments : synthetic.
- Source periods.2.household_withdrawals : synthetic.
- Source periods.2.requested_loan_disbursement : synthetic.
- Source periods.2.financed_uses : synthetic.
- Source existing_loans.0.principal : synthetic.
- Source existing_loans.0.schedule.0.principal : synthetic.
- Source existing_loans.0.schedule.0.interest : synthetic.
- Source existing_loans.0.schedule.0.fees : synthetic.
- Source existing_loans.0.schedule.1.principal : synthetic.
- Source existing_loans.0.schedule.1.interest : synthetic.
- Source existing_loans.0.schedule.1.fees : synthetic.
- Source requested_loan.principal : synthetic.
- Source requested_loan.schedule.0.principal : synthetic.
- Source requested_loan.schedule.0.interest : synthetic.
- Source requested_loan.schedule.0.fees : synthetic.
- Source requested_loan.schedule.1.principal : synthetic.
- Source requested_loan.schedule.1.interest : synthetic.
- Source requested_loan.schedule.1.fees : synthetic.

## Projet financé et résistance aux chocs — incomplet
Besoin, apport et coûts sont présentés séparément. Aucun emprunt artificiel d’apport ni baisse des dépenses essentielles n’est proposé. Les recettes attendues ne deviennent pas certaines parce qu’elles figurent au prévisionnel.
- contribution_gap : 0 XOF. Formule : max(0, apport nécessaire − apport vérifié) ; aucun apport supposé disponible.
- announced_contribution : 6000 XOF. Formule : Apport annoncé séparément de l’apport vérifié.
- required_contribution : 0 XOF. Formule : max(besoin − crédit, minimum du produit lorsqu’une politique applicable le définit).
- total_repayment : 64000 XOF. Formule : Somme du capital, des intérêts et frais exigibles sur l’échéancier complet.
- total_credit_cost : 4000 XOF. Formule : Total à rembourser − capital demandé.
- instalment_count : 2 échéances. Formule : Nombre d’échéances explicites ; ne suppose pas une durée mensuelle pour un crédit irrégulier.
- Alerte : Les recettes de projet sont prévisionnelles et nécessitent des hypothèses justifiées.
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
- Source analysis_details.project_receipts.0.amount : synthetic.
- Source analysis_details.project_receipts.0.justification.text : synthetic.
- Source analysis_details.project_receipts.0.justification.evidence_ids.0 : synthetic.

## Garanties et recouvrement — favorable
Une garantie ne corrige pas une insuffisance de capacité de paiement. Aucun taux de récupération ou LGD n’est dérivé de la valeur déclarée.
- declared_collateral_0 : 200000 XOF. Formule : Valeur déclarée, jamais assimilée à un recouvrement certain.
- known_charges_0 : 0 XOF. Formule : Charges connues, sans présumer leur exhaustivité.
- Source analysis_details.collateral.0.declared_value : synthetic.
- Source analysis_details.collateral.0.known_charges : synthetic.
- Source analysis_details.collateral.0.verification.text : synthetic.
- Source analysis_details.collateral.0.verification.evidence_ids.0 : synthetic.
- Source analysis_details.collateral.0.realization_limits.0.text : synthetic.
- Source analysis_details.collateral.0.realization_limits.0.evidence_ids.0 : synthetic.

## Historique, régularité et tendances — favorable
Des statistiques historiques ne garantissent aucun revenu futur. Saisonnalité descriptive indisponible : deux cycles annuels complets sont nécessaires ; aucune saisonnalité extrapolée.
- historical_mean : 300000 XOF. Formule : Σ valeurs / nombre de périodes comparables.
- historical_median : 200000 XOF. Formule : Valeur centrale, moyenne des deux centrales si effectif pair.
- historical_minimum : 100000 XOF. Formule : Statistique descriptive des seules observations comparables fournies.
- historical_maximum : 600000 XOF. Formule : Statistique descriptive des seules observations comparables fournies.
- historical_coefficient_of_variation : 0.7200822998230955812184408263 ratio. Formule : Écart type de population / moyenne strictement positive.
- historical_zero_income_periods : 0 périodes. Formule : Statistique descriptive des seules observations comparables fournies.
- historical_comparable_change : -0.50000000 ratio. Formule : Statistique descriptive des seules observations comparables fournies.
- Source historical_cashflows.0.receipts : synthetic.
- Source historical_cashflows.0.operating_expenses : synthetic.
- Source historical_cashflows.0.taxes : synthetic.
- Source historical_cashflows.0.essential_investments : synthetic.
- Source historical_cashflows.0.household_withdrawals : synthetic.
- Source historical_cashflows.0.requested_loan_disbursement : synthetic.
- Source historical_cashflows.0.financed_uses : synthetic.
- Source historical_cashflows.1.receipts : synthetic.
- Source historical_cashflows.1.operating_expenses : synthetic.
- Source historical_cashflows.1.taxes : synthetic.
- Source historical_cashflows.1.essential_investments : synthetic.
- Source historical_cashflows.1.household_withdrawals : synthetic.
- Source historical_cashflows.1.requested_loan_disbursement : synthetic.
- Source historical_cashflows.1.financed_uses : synthetic.
- Source historical_cashflows.2.receipts : synthetic.
- Source historical_cashflows.2.operating_expenses : synthetic.
- Source historical_cashflows.2.taxes : synthetic.
- Source historical_cashflows.2.essential_investments : synthetic.
- Source historical_cashflows.2.household_withdrawals : synthetic.
- Source historical_cashflows.2.requested_loan_disbursement : synthetic.
- Source historical_cashflows.2.financed_uses : synthetic.

## Structure financière et liquidité — incomplet
Postes et échéances fournis uniquement ; aucune transposition de ratios sans dénominateur cohérent.
- À compléter : Postes de bilan comparables et unités pour fonds de roulement, trésorerie nette et liquidité.

## Résistance aux difficultés — defavorable
Résultats conditionnels, sans estimation de probabilité de défaut.
- stress_min_margin_income-drop-20 : -223000.00 XOF. Formule : Minimum des marges recalculées sur la copie du dossier.
- Alerte : Baisse hypothétique des flux de 20 % : marge déficitaire sous ces hypothèses.

## Suggestions
- [haute] Compléter : Traitement des taxes des soldes et dénominateurs à confirmer ; Traitement des taxes des soldes et dénominateurs à confirmer ; Traitement des taxes des soldes et dénominateurs à confirmer Destinataire : analyste.
  Limites : La collecte améliore l’exploitabilité, pas une probabilité de remboursement mesurée.
- [haute] Compléter : Postes de bilan comparables et unités pour fonds de roulement, trésorerie nette et liquidité. Destinataire : analyste.
  Limites : La collecte améliore l’exploitabilité, pas une probabilité de remboursement mesurée.
- [haute] Tester un crédit de montant inférieur. Destinataire : preteur.
  Limites : Simulation conditionnelle, pas une offre ou un accord. ; Un allongement peut accroître intérêts et frais ; une réduction peut laisser un besoin non financé. ; Dépenses essentielles et dettes conservées ; aucune PD causale déduite du changement de ratio.
- [haute] Tester un allongement autorisé, en comparant la nouvelle échéance ET le coût total. Destinataire : preteur.
  Limites : Simulation conditionnelle, pas une offre ou un accord. ; Un allongement peut accroître intérêts et frais ; une réduction peut laisser un besoin non financé. ; Dépenses essentielles et dettes conservées ; aucune PD causale déduite du changement de ratio.
- [haute] Examiner la variante testée, sans modifier les faits du dossier ni masquer une dette. Destinataire : analyste.
  Limites : Comparer échéances et coût total ; une durée supérieure peut augmenter les intérêts. ; Le maximum compatible parmi les candidats testés n’est pas le financement conseillé.
- [haute] Examiner la variante testée, sans modifier les faits du dossier ni masquer une dette. Destinataire : analyste.
  Limites : Comparer échéances et coût total ; une durée supérieure peut augmenter les intérêts. ; Le maximum compatible parmi les candidats testés n’est pas le financement conseillé.

## Décision du prêteur
Non fournie. Ce rapport n’est pas un accord bancaire.

