# Validation de l'intégration PDF — 4 novembre 2026

## Installation observée

- Hôte Debian GNU/Linux 13.6, Linux x86_64 ; Python 3.12.14 dans `/workspace/.venv`.
- Archive extraite sous `modules/credit_pme_pdf/`, sans écrasement de fichier existant.
- Aucun `AGENTS.md` trouvé dans le dépôt. README, INTEGRATION et TEST_REPORT du module lus.
- Installation du paquet local par `uv lock`, puis `uv sync --locked`.
- Versions FastAPI 0.115.12, Pydantic 2.11.4, SQLAlchemy 2.0.40, Alembic 1.15.2,
  psycopg 3.2.9 et uvicorn 0.34.2 identiques avant/après (comparaison automatisée).
- PyMuPDF 1.26.6, pdfplumber 0.11.9, ReportLab 4.4.9 installés et verrouillés.
- `uv pip check` : 38 paquets contrôlés, dépendances compatibles.
- Tesseract hôte 5.5.0 déjà présent, `fra` initialement absent. Modèle français officiel
  installé sans privilèges dans `.local/share/tessdata`, empreinte contrôlée. Les
  configurations `configs/tsv` et `tessconfigs` sont liées depuis l'installation système.
- Image Docker construite avec Tesseract et `tesseract-ocr-fra` ; `--list-langs`
  dans le conteneur retourne `eng`, `fra`, `osd`. Migration en production locale : `0002 (head)`.

## Tests réellement exécutés

| Commande / contrôle | Résultat final |
|---|---|
| Depuis `modules/credit_pme_pdf`, `../../.venv/bin/python -m unittest discover -s tests -v`, `TESSDATA_PREFIX` exporté | 167 tests réussis en 7,079 s, aucun ignoré |
| Depuis la racine, `.venv/bin/python -m pytest -q` sur SQLite temporaire | 48 tests réussis |
| Même suite avec `TEST_DATABASE_URL=…/credit_test` sur PostgreSQL | 48 tests réussis |
| `.venv/bin/ruff check .` | Réussi |
| `.venv/bin/ruff format --check .` | 29 fichiers déjà formatés ; code fourni du module exclu du reformatage |
| `bash -n scripts/install_pdf_ocr.sh`, puis exécution du script sur installation existante | Réussis |
| CLI `extract` sur les cinq exemples demandés | 5 JSON produits, y compris OCR français réel |
| CLI `batch examples/manifest.json --ocr never` (chemin du module) | 132/132 documents, aucun échec |
| `scripts/verify_pdf_examples.py` | Tous les contrôles de montants, pages, colonnes et avertissements réussis |
| Construction Docker avec certificat proxy monté en secret | Réussie |
| `scripts/demo_pdf_api.py` sur HTTP réel | 5 pièces extraites et persistées dans 2 dossiers, sans modifier leurs données ou analyses |
| `compose restart db api`, puis `scripts/demo_pdf_api.py --verify-existing` | 5 résultats, 2 dossiers et 2 analyses strictement identiques |
| Comparaison des 4 anciennes analyses du socle après migration | Instantanés conservés à l'identique |

Les tests d'intégration ajoutés contrôlent les deux noyaux, le catalogue, la
conservation de l'original, les empreintes, la relecture après recréation de
l'application, l'absence d'ingestion financière, les dossiers croisés/inexistants,
les métadonnées invalides, le MIME, les tailles déclarées et réellement lues,
les corps incomplets, les PDF invalides/chiffrés, 101 pages refusées, la saturation
à deux traitements et les erreurs internes sans fuite de contenu.
Les migrations aller/retour sont exécutées sur SQLite et sur une base PostgreSQL
**dédiée aux tests**. La base existante de démonstration n'a pas été effacée.

La suite d'origine contient un test OCR explicitement anglais ; il est conservé et
réussi, sans substitution au français. L'OCR français est vérifié séparément sur
le bulletin scanné, en CLI puis dans le conteneur via l'API réelle.

## Résultats des cinq pièces

| Pièce synthétique | Constat vérifié |
|---|---|
| `payslip_detail.pdf` | Net `280000 XOF`, page 1, preuve `p1:l6`, méthode native |
| `bank_table.pdf` | Colonnes Date/Libellé/Débit/Crédit distinctes ; crédit `280000`, débit `60000`, page 1 ; cellule vide conservée `null`, devise de cellule non inventée |
| `balance_multiyear.pdf` | Colonnes 2026/2025 séparées : actif `1200` / `900` ; pas de concaténation ni de multiplication automatique ; statut ambigu et avertissement d'échelle conservés |
| `form.pdf` | Champ interactif `montant_demande=150000`, page 1 ; pas de conversion automatique en entrée financière |
| `payslip_scan.pdf` | OCR **fra** : net `280000 XOF`, page 1 ; avertissement de revue visuelle et statut non vérifié conservés |

Les JSON et journaux actuels sont dans `output/pdf/`, exclu par `.gitignore` et
`.dockerignore`. Les cinq réponses HTTP et l'état de relecture sont dans
`output/pdf/api/`. Les résultats fournis dans `modules/credit_pme_pdf/examples/results`
restent les artefacts de l'archive ; ils ne sont pas présentés comme les nouvelles exécutions.

## Incidents corrigés et limites

La première exécution OCR locale ne produisait pas de candidats : le modèle était
présent mais sa configuration TSV manquait dans le dossier personnalisé. Les liens
vers les configurations système ont corrigé ce problème, et les tests ont été relancés.
La comparaison des dates SQLite a révélé la perte du fuseau au rechargement ; les
métadonnées de documents normalisent désormais leurs dates en UTC. Le test de saturation
PostgreSQL utilisait initialement une URL dont le mot de passe était masqué par SQLAlchemy ;
ce test a été corrigé sans modifier les identifiants de la base.

Un avertissement de dépréciation Starlette TestClient / AnyIO `BlockingPortal` reste
présent ; aucun test en échec. Les permissions réseau du bac à sable étaient nécessaires
pour les téléchargements et tests HTTP. Aucun téléchargement ou service nécessaire
ne reste bloqué à la fin de cette validation.

Aucun PDF personnel ou bancaire réel n'a été testé. Pas de mesure de précision terrain,
de validation de documents authentiques, de revue humaine authentifiée, de test de charge,
de protection multitenant ni d'isolation CPU/mémoire. Le résultat reste non vérifié et
n'alimente ni calcul, score, recommandation ni entraînement. L'installation locale `fra`
éxige l'export `TESSDATA_PREFIX` ; Docker utilise son modèle français système.

## Fichiers livrés ou modifiés

- `modules/credit_pme_pdf/` : 162 fichiers de l'archive, comparés octet par octet et inchangés.
- `credit/documents/contracts.py`, `service.py`, `routes.py` : contrats, extraction et routes.
- `credit/api.py`, `credit/persistence.py` : branchement API et table des pièces.
- `migrations/versions/0002_pdf_documents.py` : migration des originaux et extractions.
- `pyproject.toml`, `uv.lock` : paquet local, dépendances verrouillées et tests séparés.
- `Dockerfile`, `.dockerignore`, `.gitignore` : installation OCR dans l'image et exclusions.
- `tests/test_documents.py` : tests de l'intégration PDF.
- `tests/conftest.py`, `tests/test_api.py` : mutualisation de la fixture de base migrée.
- `scripts/install_pdf_ocr.sh`, `scripts/verify_pdf_examples.py`, `scripts/demo_pdf_api.py` : installation et vérifications reproductibles.
- `README.md`, `VALIDATION.md`, `docs/EXTRACTION_PDF.md`, `docs/VALIDATION_PDF.md` : commandes, résultats et limites.
- `.local/share/tessdata/`, `output/pdf/` : modèle installé et résultats d'exécution, exclus du suivi.
