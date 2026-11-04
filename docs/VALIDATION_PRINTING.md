# Validation des éditions imprimables — 4 novembre 2026

Environnement : Linux, Python 3.12, PostgreSQL 16.6, ReportLab 4.4.9,
PyMuPDF 1.26.6. Dossiers et documents exclusivement synthétiques.

## Vérifications exécutées

- Suite finale projet sur SQLite : **181 tests réussis**, dont 44 tests d’impression.
- Suite finale projet sur PostgreSQL dédié `credit_test` : **181 tests réussis**.
- Module PDF, lancé depuis `modules/credit_pme_pdf` : 167 tests réussis.
- Vérification Ruff du dépôt : aucune erreur ; formatage conforme.
- `uv lock --check --offline` : résolution verrouillée cohérente, 41 paquets.
- Une dépréciation Starlette/AnyIO reste signalée, sans échec de test.

Les tests d’impression génèrent réellement les PDF des modèles applicables aux
deux noyaux, puis extraient leur texte. Ils couvrent états inconnus / zéro /
non applicable, montants, accents, dates, contenus incomplets, absence de score
inventé, indicateurs, scénarios et coût, absence de recalcul financier, projection
demandeur avant rendu, droits par dossier et institution, immutabilité des PDF,
versions, publication explicite, échappement des commentaires et refus des
ressources distantes, limites, attente / échec, logos contrôlés, liens de retour
signé distinct et journal des téléchargements.

Le test de commentaire commençant par une date empêche sa conversion erronée en
simple date d’affichage. Le test de restitution demandeur vérifie aussi qu’une
analyse incomplète garde ce statut sans exposer les observations internes.

## Parcours réel

La migration `0005` a été appliquée à la base PostgreSQL du service local.
Le serveur natif sur `127.0.0.1:8002` a créé quatre dossiers, leurs analyses et
17 éditions HTML/PDF, avec vérification des empreintes et dossiers inchangés.
L’image Docker a été reconstruite avec ReportLab en dépendance d’exécution,
les certificats du proxy et `uv sync --locked --no-dev`.
Le parcours a ensuite été exécuté sous Docker : 17 éditions complètes et
empreintes cohérentes. Après redémarrage conjoint de PostgreSQL et de l’API,
les 17 fichiers et leurs métadonnées ont été retrouvés à l’identique.
Une lecture lancée pendant le redémarrage a rencontré une déconnexion ;
le contrôle a réussi après retour de `/health` à `ok`.
`alembic current` confirme `0005 (head)` et le conteneur fournit ReportLab 4.4.9.

Les scripts gardent leurs journaux et réponses dans `output/printing/`, ignoré
par Git. Les téléchargements exigent toujours un jeton et l’accès au dossier.
Aucun partage externe n’a été effectué.

## Revue des PDF livrés

`examples/printing/generate.py` a généré neuf PDF et leurs aperçus HTML.
`inspect_printing.py` a vérifié le texte, la pagination et les limites géométriques
sur chacune des 53 pages finales, puis rendu chaque page en image monochrome.
Les neuf planches regroupant toutes ces pages ont été inspectées visuellement.

| Exemple | Pages |
|---|---:|
| Restitution demandeur sans résultats autorisés | 2 |
| Déclaration financière entreprise | 2 |
| Rapport détaillé PME avec alertes et tableaux | 23 |
| Plan d’amélioration | 4 |
| Dossier particulier complet | 6 |
| Budget incomplet | 3 |
| Nom et commentaire longs | 4 |
| Synthèse particulière | 2 |
| Rapport de simulation | 7 |

Les montants et accents sont lisibles, les tableaux restent dans les marges,
les en-têtes se répètent sur les pages suivantes, les bas de page portent
l’identifiant et la pagination. Les zones de signature sont vierges. Les longs
commentaires sont conservés, découpés en cellules de continuation. Le contrôle
visuel a conduit à compacter les tableaux du budget et supprimer les doublons de
périodes du dossier complet. Les documents riches restent volontairement longs ;
certaines pages de fin contiennent peu de texte ou une zone de signature.

Le parcours de correction OCR a aussi été prolongé jusqu’au PDF : la transcription
revue à 280 000 FCFA est imprimée depuis l’instantané d’analyse, avec identifiant de
revue et auteur, sans changer les 500 000 FCFA déclarés dans le dossier. Ce test
complémentaire a réussi sur SQLite et PostgreSQL.

Le texte du PDF est sélectionnable et recherchable : contrôle avec PyMuPDF,
sans OCR. Le moteur de rendu utilise un même contrat de présentation pour HTML
et PDF, avec échappement dans les deux sorties. Aucune capture d’écran n’est
utilisée pour fabriquer les PDF.

La pagination physique d’une imprimante et la boîte de dialogue d’impression
d’un navigateur n’ont pas été testées. Les styles HTML sont fournis ; la
pagination garantie est celle des PDF inspectés.

## Fichiers ajoutés / adaptés

- `credit/printing/` : catalogue, profils descriptifs, présentation filtrée,
  rendus HTML/PDF, worker isolé, orchestration, versions, API.
- `credit/individuals/contracts.py`, `credit/businesses/contracts.py` :
  champs descriptifs facultatifs `record_details`.
- `credit/auth.py`, `credit/api.py`, `credit/persistence.py` : droits analyste,
  institution du dossier, intégration des routes et stockage privé des éditions.
- `migrations/versions/0005_print_editions.py` : trois tables d’édition/audit/
  publication et colonne d’institution.
- `pyproject.toml`, `uv.lock` : version 0.4.0, ReportLab en dépendance d’exécution.
- `compose.yaml`, `.env.example`, `scripts/init_local_auth.py` : configuration
  d’impression et identité institutionnelle facultative.
- `tests/test_printing.py`, extension de `tests/test_assessment_api.py`,
  `scripts/demo_printing.py`, `scripts/inspect_printing.py`.
- `examples/printing/` : quatre dossiers, générateur, neuf HTML et neuf PDF.
- README, guide `DOCUMENTS_IMPRIMABLES.md` et cette note de vérification.

## Limites

Aucun frontend n’existe dans le projet ; pas de nouveau frontend complet.
Pas de signature électronique certifiée, d’authentification automatique des pièces,
de grille métier validée ou modèle prédictif ajouté. Aucune décision bancaire.
Le registre d’identités reste local, pas un SSO multi-institution en production.
Le worker est isolé dans un processus avec limites Linux et réseau refusé ;
il n’est pas un service conteneurisé distinct à privilèges réduits. Après arrêt
brutal, une édition peut rester `processing` et nécessite un examen technique.
Le stockage privé utilise la base existante, sans chiffrement applicatif.
