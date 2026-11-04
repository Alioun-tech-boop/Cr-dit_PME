# Vérifications exécutées le 4 novembre 2026

Environnement : Python 3.12.14, PostgreSQL 16.6 via Docker, dépendances du fichier
`uv.lock`. Les commandes Python ci-dessous ont été exécutées avec `.venv/bin/…`
après `uv sync --locked`.

| Vérification | Résultat observé |
|---|---|
| Installation `uv sync --locked` | Réussie |
| `pytest -q` sur SQLite temporaire | 35 tests réussis |
| `TEST_DATABASE_URL=…/credit_test pytest -q` sur PostgreSQL | 35 tests réussis |
| `ruff check .` | Réussi |
| `ruff format --check .` | 22 fichiers déjà formatés |
| Construction de l'image Docker finale | Réussie avec certificat du proxy monté en secret |
| Démarrage Compose, migrations et `/health` | Réussis |
| `scripts/demo.py` sur HTTP réel | 4 dossiers, 4 analyses de base et 4 scénarios créés |
| Remplacement des 4 dossiers par PUT | Instantanés d'analyses historiques inchangés |
| Redémarrage des conteneurs PostgreSQL et API | 4 instantanés complets identiques, 8 analyses/scénarios retrouvés |

La suite vérifie les calculs nominaux, inconnus et non applicables, montants et
périodes invalides, ratios non calculables, capital et arrondis des prêts à taux
nul et positif, échéances irrégulières, dettes dupliquées, retenues salariales,
coûts professionnels, prélèvements du ménage, financement/emploi, stress et retard,
provenance contradictoire, devises, indisponibilité des scores, routes et historique.
Les tests API appliquent `upgrade head` et `downgrade base` sur leur base dédiée.
L'API réelle conserve ses données dans un volume PostgreSQL distinct de cette base.

Un avertissement de dépréciation provient de l'interaction Starlette TestClient /
AnyIO (`BlockingPortal`) ; aucun test en échec. Il ne modifie pas les calculs.

L'installation initiale et TestClient demandaient les permissions réseau du bac à
sable. Docker a temporairement saturé le disque avec son pilote VFS : seuls les
caches et images obsolètes de cette session ont été nettoyés, puis les copies du
Dockerfile regroupées. La construction finale et le redémarrage ont ensuite réussi.
Aucun service requis ne reste bloqué au terme des vérifications.

Les contrôles de production (charge, isolation des utilisateurs, sécurité, sauvegarde
et restauration hors machine) n'ont pas été exécutés. La revue métier et la
validation réglementaire des hypothèses restent à faire. Aucun modèle prédictif
ni grille d'accord n'a été entraîné, validé ou activé.

L'étape PDF ultérieure possède son propre rapport :
[docs/VALIDATION_PDF.md](docs/VALIDATION_PDF.md), avec 167 tests du module,
48 tests du backend sur SQLite et PostgreSQL, et OCR français vérifié.

Le parcours de dépôt v0.2 est validé séparément dans
[docs/VALIDATION_SCANS.md](docs/VALIDATION_SCANS.md) : 77 tests du projet sur chaque
base, 167 tests du module et vérification HTTP des sources/revues après redémarrage.
