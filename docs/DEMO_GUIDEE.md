# Démonstration guidée Crédix

Depuis l’accueil de la plateforme, ouvrir **Lancer la démonstration**. Deux parcours en lecture seule sont disponibles :

1. **Particulier salarié** : revenus, dépenses, dettes, réserve, historique, analyse sur six périodes, choc de baisse de 20 %, recherche inverse et variantes de durée.
2. **PME de commerce** : données comptables, encaissements, charges, taxes, cycle d’exploitation, tension de trésorerie, choc de baisse de 20 % et variantes non compatibles ou incomplètes.

## Étapes présentées

- Constitution et besoin de financement.
- Données financières par période.
- Qualité documentaire et pièces attendues.
- Analyse financière déterministe v2 et sous-analyses.
- Scénarios de stress, recherche inverse et variantes de financement.
- Restitution, informations manquantes et limites de décision.

## Nature des données et limites

Les rapports sont des extraits compacts des exemples versionnés :
- \`examples/assessments/individual_control.json\` et \`examples/financial_v2/individual_control.report.json\`
- \`examples/assessments/business_profitable_cash_tension.json\` et \`examples/financial_v2/business_profitable_cash_tension.report.json\`

La démonstration est statique, publique et en lecture seule : elle n’appelle aucune API, ne crée aucun dossier, n’enregistre aucun document et ne touche pas aux données connectées de l’utilisateur. Les références documentaires sont synthétiques ; l’authenticité n’est pas évaluée et aucun document réel n’est joint. L’écran documentaire explique les pièces attendues sans prétendre simuler un OCR ou une revue qui n’a pas été exécutée.

Les politiques des rapports sont \`illustrative_not_validated\`. Le score est indisponible, le modèle statistique est désactivé, aucune PD ni perte attendue n’est calculée, et aucune décision de crédit n’est rendue. Les variantes présentées ne constituent ni une offre commerciale ni une recommandation de financement.

## Vérification

Depuis \`frontend/\` :

\`\`\`bash
npm test
\`\`\`

Le test dédié vérifie la présence des deux dossiers, des rapports v2, des principales valeurs financières, des garde-fous et du branchement dans le routeur.
