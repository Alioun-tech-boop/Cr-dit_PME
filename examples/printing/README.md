# Exemples imprimables synthétiques

Ces fichiers ne contiennent aucun dossier client réel. Les PDF sont du texte natif,
avec les mêmes données que leurs aperçus HTML. Les états financiers déclaratifs
ne sont pas certifiés et les rapports ne constituent pas un accord de crédit.

- [Dossier particulier complet](individual_fields.pdf)
- [Budget incomplet](individual_incomplete.pdf)
- [Synthèse en deux pages](individual_summary.pdf)
- [Déclaration financière PME](business_financial.pdf)
- [Rapport détaillé PME avec alertes](business_report.pdf)
- [Plan d’amélioration](improvement_plan.pdf)
- [Simulation chiffrée](simulation.pdf)
- [Nom et commentaire longs](individual_long.pdf)
- [Version demandeur, résultats non autorisés](applicant_analysis.pdf)

Régénération depuis la racine :

```bash
.venv/bin/python examples/printing/generate.py
.venv/bin/python scripts/inspect_printing.py
```

Les quatre JSON sont des exemples de saisie. Les analyses sont fournies par les
moteurs existants ; les gabarits n’en recalculent pas les scores. Les exemples de
politique portent explicitement « ILLUSTRATIF — NON VALIDÉ ».
