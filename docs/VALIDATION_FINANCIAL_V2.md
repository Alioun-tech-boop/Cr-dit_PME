# Vérifications exécutées — financial_analysis_v2

Date : 5 novembre 2026. Données exclusivement synthétiques. Environnement Linux,
Python 3.12, SQLite isolée pour les tests et les parcours navigateur. Aucun essai
contre une institution ou un demandeur réel, aucun déploiement extérieur.

| Commande exécutée | Résultat constaté |
|---|---|
| `.venv/bin/pytest -q` avant modification | 257 réussis, 2 avertissements de dépréciation, 90,56 s |
| `.venv/bin/pytest -q` après corrections finales | **288 réussis**, 2 avertissements de dépréciation Starlette/AnyIO, 105,81 s |
| `.venv/bin/pytest -q tests/test_financial_v2.py` | 31 nouveaux tests réussis sur la version testée ; ils sont également inclus dans les 288 de la dernière suite complète |
| Depuis `modules/credit_pme_pdf/` : `../../.venv/bin/python -m unittest discover -s tests -v` | **167 tests réussis**, 7,34 s |
| Depuis `frontend/` : `npm test` | 30 contrôles de contrats, 42 de livraison/transport, 3 de frontières asynchrones réussis |
| `.venv/bin/python -m scripts.run_frontend_e2e` | **54 contrôles Chromium réussis**, aucune erreur JavaScript ; deux noyaux, session, reprise, documents, OCR/revue, analyse v2, simulation, PDF, publication, accès et conflits ; zone prédictive absente du nouveau rendu |
| `.venv/bin/ruff check credit tests scripts examples/financial_v2/generate.py` | Aucun problème signalé |
| `git diff --check` | Aucun problème signalé |
| `.venv/bin/python -m examples.financial_v2.generate` | Quatre rapports JSON/texte, cinq PDF et leurs aperçus HTML réellement générés |
| `.venv/bin/python -m scripts.validate_financial_v2_pdfs` | Texte extrait de chaque page et rendus produits : 56 pages au total, aucune page sans texte |

Les fichiers de sortie, journaux et planches de contrôle sont dans
`output/financial-v2/`, exclu de Git. Les exemples partageables restent dans
`examples/financial_v2/`. Les planches de toutes les pages ont été inspectées :
présence des tableaux, titres, pieds et pagination ; cela ne remplace pas une recette
d’impression sur toutes les imprimantes ou un examen de chaque caractère en pleine
résolution. Le rapport détaillé est volumineux car il conserve les valeurs sources
et règles ; les synthèses des dossiers complets d’exemple tiennent sur deux pages,
le dossier incomplet sur trois. La couverture du rapport détaillé est peu remplie.

## Résultats financiers de contrôle

- Particulier : `500000 − 300000 − 50000 − 80000 = 70000` FCFA.
- Baisse de 20 % : `400000 − 300000 − 50000 − 80000 = −30000` FCFA.
- Revenu annulant la marge : `430000` FCFA ; baisse de `14 %`.
- Entreprise : `4000000 − 3000000 = 1000000` FCFA disponibles pour dette ;
  marge `1000000 − 250000 − 400000 = 350000` ; couverture `1000000 / 650000`.

Les tests couvrent aussi la conservation des encaissements retardés, la séparation
fixe/variable, les retenues salariales, les unités comptables, les capitaux propres
négatifs, les déficits saisonniers, les inconnues, les variantes sans solution,
les coûts de durée, l’apport sans double comptage, les dérogations tracées et la
non-mutation des dossiers et rapports historiques. Les contrôles existants sur
les transferts internes, devises, échéanciers et pièces OCR restent exécutés.

## Limites de cette validation

La suite finale de ce parcours utilise SQLite et une passerelle locale. Une nouvelle
recette de concurrence PostgreSQL et de charge en environnement de déploiement n’a
pas été effectuée ici. Aucun agrément BCEAO, aucune calibration bancaire ni politique
de prêteur réelle approuvée n’est fourni. Les politiques livrées sont illustratives
et refusées sur des dossiers réels. Le paramétrage avancé de l’interface est en JSON.
Le moteur n’est pas un solveur global de financement : les candidats et les intervalles
sont bornés et explicitement fournis. Les conventions complexes de taux variable,
change multi-devises et différés capitalisant les intérêts restent hors périmètre.
