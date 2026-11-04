# Vérifications du moteur par sections

Exécution le 4 novembre 2026, Linux, Python 3.12, PostgreSQL 16.6,
Tesseract 5.5 avec `fra`. Documents et dossiers exclusivement synthétiques.

## Commandes exécutées

```bash
TESSDATA_PREFIX=/workspace/.local/share/tessdata .venv/bin/python -m pytest -q --tb=short
TEST_DATABASE_URL=postgresql+psycopg://credit:credit_local@127.0.0.1:5432/credit_test \
  TESSDATA_PREFIX=/workspace/.local/share/tessdata \
  .venv/bin/python -m pytest -q --tb=short
(cd modules/credit_pme_pdf && \
  TESSDATA_PREFIX=/workspace/.local/share/tessdata \
  ../../.venv/bin/python -m unittest discover -s tests -v)
.venv/bin/ruff check .
.venv/bin/ruff format --check credit tests scripts examples/assessments
.venv/bin/python examples/assessments/generate.py
.venv/bin/python scripts/demo_assessments.py --base-url http://127.0.0.1:8001
.venv/bin/python scripts/demo_assessments.py
.venv/bin/python scripts/demo_assessments.py --verify-existing
```

Attention : `credit_test` est une base dédiée, dont les tables sont supprimées par
les fixtures. Ne jamais pointer `TEST_DATABASE_URL` vers la base de dossiers.

La suite du projet couvre les sept/neuf sections, cas manquants et non applicables,
unités/devises, ratios nuls, retenues et BFR sans double comptage, déficits saisonniers,
flux datés, politiques et modèles incompatibles, coûts de durée, suggestions sous
stress, revue de transcription et sources, droits et conservation des instantanés.
Les faux modèles des tests sont des adaptateurs synthétiques : aucun modèle réel
n’a été entraîné, calibré ou validé.

## Résultats

- Projet sur SQLite : **137 tests réussis**.
- Projet sur PostgreSQL dédié : **137 tests réussis**.
- Module PDF : **167 tests réussis** depuis son dossier.
- Ruff : aucune erreur ; vérification de format : 57 fichiers conformes.
- Un avertissement de dépréciation Starlette/AnyIO reste présent, sans échec.

## Vérification HTTP et déploiement local

- Migration appliquée sur PostgreSQL réel ; `alembic current` retourne `0004 (head)`.
- Image `workspace-api` reconstruite avec CA du proxy et dépendances verrouillées.
- Compose démarré ; `/health` retourne `{"status":"ok"}` ; Tesseract liste `fra`.
- Quatre dossiers, quatre rapports (sept ou neuf sections), trois simulations
  créés par HTTP sur serveur Python puis sur Docker.
- Marge individuelle 70 000.00 XOF ; après baisse de revenu de 20 %, −30 000.00 XOF.
- Tous les rapports de démonstration ont `model_status=not_available`, score combiné
  et PD absents. Un dossier incomplet ne reçoit pas de score par critères.
- Les onze réponses dossiers/analyses/simulations sont identiques après redémarrage
  de PostgreSQL et API, puis après un second redémarrage de l’API seule.
- Originaux structurés inchangés après simulation ; coût calculable d’une durée
  allongée conservé, projections futures demandées explicitement.

Un premier passage PostgreSQL (136 tests avant le dernier test ajouté) a réussi.
Un passage suivant a été interrompu par notre redémarrage du conteneur PostgreSQL :
136 succès, un échec `AdminShutdown`. Le passage final séparé a réussi : 137 tests,
sans redémarrage simultané. Les journaux locaux sont dans `output/pdf/` (hors Git).

## Inventaire des changements

- `credit/assessment/` : contrats, orchestration, contexte, règles communes,
  scoring, registre versionné, simulations, suggestions, rapports et routes.
- `credit/individuals/sections.py`, `credit/businesses/sections.py` : analyseurs métier.
- Contrats des deux noyaux et `credit/shared/` : compléments de données, preuves,
  montants signés, périodes observées/prévisionnelles, échéanciers et filtrage OCR.
- `credit/api.py`, `credit/config.py`, `credit/persistence.py` et migration `0004`.
- `.env.example`, `compose.yaml`, `pyproject.toml`, `uv.lock`, `.gitignore` :
  version 0.3, mode démonstration explicite, inclusion Git du domaine partagé.
- `examples/assessments/` : quatre dossiers et huit restitutions JSON/Markdown,
  générateur reproductible ; `scripts/demo_assessments.py` : parcours HTTP.
- `tests/test_assessments.py`, `tests/test_assessment_api.py` : tests ajoutés.
- README et guides français d’analyse et de validation.

## Limites

Pas de politique métier approuvée fournie, ni de modèle prédictif, PD, décision
bancaire ou frontend. Les pondérations sont illustratives et refusées pour les
dossiers réels. Les agrégats doivent être rapprochés et exclure les transferts
internes. La revue documentaire confirme la transcription, sans authentification.
La prochaine étape est une revue métier des formules, seuils, produits et preuves,
puis l’approbation explicite d’une grille par profil avant usage réel.
