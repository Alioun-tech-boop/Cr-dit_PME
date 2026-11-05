# Cr-dit_PME

# Crédit PME — backend et frontend locaux

Le frontend est connecté par une passerelle de même origine : connexion par cookie
HttpOnly, brouillons persistants, pièces, revue, analyses publiées, simulations et
PDF. Voir [installation et vérifications](docs/FRONTEND_BACKEND.md).
Les identités navigateur sont provisionnées côté serveur ; aucun Bearer technique
n’est envoyé au navigateur.

L’audit v0.5 et les corrections de sécurité/fiabilité sont décrits dans
[docs/security/AUDIT.md](docs/security/AUDIT.md), avec
[matrice des droits](docs/security/PERMISSIONS.md),
[formules auditées](docs/security/FORMULES.md) et
[procédure de restauration](docs/security/BACKUP_RESTORE.md).
Les modifications de dossier exigent désormais `If-Match` avec leur `version`.

Les éditions imprimables v0.4 (HTML, PDF, versions demandeur/analyste) sont décrites
dans [docs/DOCUMENTS_IMPRIMABLES.md](docs/DOCUMENTS_IMPRIMABLES.md).
Des [PDF synthétiques](examples/printing/) sont fournis et leurs vérifications sont
consignées dans [docs/VALIDATION_PRINTING.md](docs/VALIDATION_PRINTING.md).

Le moteur v0.3 ajoute les analyses par sections, politiques explicites, suggestions
et simulations : [guide et commandes](docs/ANALYSE_SECTIONS.md),
[vérifications exécutées](docs/VALIDATION_ASSESSMENTS.md).

Le parcours de dépôt v0.2 (identités, politiques, images/PDF, pages, OCR et revue)
est documenté dans [docs/PARCOURS_SCANS.md](docs/PARCOURS_SCANS.md). Les anciennes
routes d’envoi direct de PDF sont retirées (410), leurs lectures restent disponibles.
Les exemples curl ci-dessous exigent désormais le jeton d’un agent autorisé.

Backend fonctionnel d'analyse déterministe du crédit au Burkina Faso : particuliers
(salariés, retraités, indépendants) et entreprises (comptabilité structurée ou flux
reconstitués). Aucun avis d'accord automatique. Cette version n'est pas prête pour
la production.

## Démarrage avec Docker Compose

Prérequis : Docker avec Compose v2, ports locaux 8000 et 5432 libres.

```bash
[ -f .env ] || cp .env.example .env
uv sync --locked
# Une seule fois, si cette identité n’existe pas encore :
.venv/bin/python scripts/init_local_auth.py --user agent-scans --reviewer
CREDIT_AUTH_JSON="$(cat .local/auth/users.json)" docker compose up --build -d
curl --fail http://127.0.0.1:8000/health
```

Attendre la disponibilité de l'API après la construction. Swagger :
http://127.0.0.1:8000/docs. Les migrations Alembic sont appliquées au démarrage de
l'API. PostgreSQL utilise le volume `credit_data` : `docker compose down` le conserve.
`docker compose up -d` retrouve les dossiers et analyses. Ne pas utiliser `down -v`
si les données doivent être conservées.

Dans un environnement cloud avec une autorité de certification du proxy, construire
avec le bundle de confiance fourni (aucune désactivation TLS) :

```bash
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -t workspace-api .
CREDIT_AUTH_JSON="$(cat .local/auth/users.json)" docker compose up -d --no-build
```

Le nom d'image par défaut de Compose dépend du nom du répertoire : remplacer
`workspace-api` par `<nom-du-projet-compose>-api` si nécessaire.

## Installation Python et tests

Python 3.12 recommandé (testé avec 3.12.14), uv 0.9.8 utilisé dans l'image.
Versions directes dans `pyproject.toml` et résolution transitive figée dans `uv.lock`.

```bash
python -m pip install uv==0.9.8
uv sync --locked
uv run pytest -q
uv run ruff check .
```

Les tests par défaut appliquent puis annulent les migrations sur SQLite temporaire,
exercent les deux moteurs et les routes, et recréent l'application pour vérifier
l'historique. Pour vérifier aussi PostgreSQL, utiliser une base dédiée **jetable** :
les tests créent et suppriment leurs tables dans cette base.

```bash
docker compose up -d db
docker compose exec -T db createdb -U credit credit_test
TEST_DATABASE_URL=postgresql+psycopg://credit:credit_local@127.0.0.1:5432/credit_test uv run pytest -q
```

Pour lancer l'API Python sur PostgreSQL sans conteneur API :

```bash
docker compose up -d db
export DATABASE_URL=postgresql+psycopg://credit:credit_local@127.0.0.1:5432/credit
uv run alembic upgrade head
CREDIT_AUTH_FILE=/workspace/.local/auth/users.json uv run uvicorn credit.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

`.env` est lu par Compose ; le lancement Python utilise les variables exportées,
pas une lecture implicite du fichier. Dans le bac à sable de travail, les tests HTTP
peuvent nécessiter les permissions réseau locales (TestClient utilise les primitives
asynchrones du système). Les calculs purs n'en ont pas besoin.

## Soumettre les quatre dossiers synthétiques

```bash
uv run python scripts/demo_scans.py --user agent-scans
```

Le démonstrateur actuel crée deux dossiers, leurs dépôts, traitements et revue
sans changer leurs analyses. Les quatre dossiers JSON financiers d’origine restent fournis. Données : `examples/salarie.json`,
`independant.json`, `pme_structuree.json`, `petite_activite.json`.
`uv run python examples/generate.py` les régénère. Tous les noms, références et montants
sont synthétiques.

Exemples curl, remplacer les identifiants par ceux retournés :

```bash
curl --config .local/auth/cda4d66fbf09672f.curl --fail -X POST http://127.0.0.1:8000/individuals \
  -H 'Content-Type: application/json' --data-binary @examples/salarie.json
curl --config .local/auth/cda4d66fbf09672f.curl --fail -X POST http://127.0.0.1:8000/individuals/ID_DOSSIER/analyses
curl --config .local/auth/cda4d66fbf09672f.curl --fail http://127.0.0.1:8000/analyses/ID_ANALYSE
curl --config .local/auth/cda4d66fbf09672f.curl --fail http://127.0.0.1:8000/individuals/ID_DOSSIER/analyses
curl --config .local/auth/cda4d66fbf09672f.curl --fail -X POST http://127.0.0.1:8000/businesses \
  -H 'Content-Type: application/json' --data-binary @examples/pme_structuree.json
curl --config .local/auth/cda4d66fbf09672f.curl --fail -X POST http://127.0.0.1:8000/businesses/ID_DOSSIER/scenarios \
  -H 'Content-Type: application/json' \
  -d '{"name":"Retard illustratif","revenue_drop":"0.10","delay_from":"2026-02-01","delay_to":"2026-03-01","delay_amount":"50000"}'
```

| Opération | Route |
|---|---|
| Créer un dossier | `POST /individuals`, `POST /businesses` |
| Lire / remplacer un dossier | `GET`, `PUT /individuals/{id}` ou `/businesses/{id}` |
| Analyser / simuler | `POST /{noyau}/{id}/analyses`, `POST /{noyau}/{id}/scenarios` |
| Lister l'historique | `GET /{noyau}/{id}/analyses` |
| Lire un instantané complet | `GET /analyses/{id}` |
| Vérifier la base | `GET /health` |

Une analyse contient les résultats par période, informations à demander, constats
financiers, qualité documentaire séparée, hypothèses et scores indisponibles.
La lecture historique ajoute l'entrée, les preuves, la configuration, la date et
la version du moteur. Un `PUT` change seulement le dossier ; aucune route ne modifie
une analyse historique. Un scénario crée également une nouvelle analyse persistée.
Un POST répété crée une nouvelle ressource : pas d'idempotence automatique.

## Organisation

- `credit/individuals`, `credit/businesses` : contrats et calculs purs distincts.
- `credit/shared` : preuves, montants, scénarios, résultats, échéanciers et interfaces de score.
- `credit/application.py` : orchestration et instantanés.
- `credit/documents/` : extraction PDF, rattachement explicite et consultation sans ingestion financière.
- `credit/persistence.py`, `migrations/` : SQLAlchemy et Alembic, documents JSON validés.
- `credit/api.py`, `credit/config.py` : routes, suivi technique et configuration.
- `tests/`, `examples/`, `scripts/` : validation et démonstration.

Les moteurs sont directement appelables sans HTTP ni base. Exemple du générateur :

```python
from datetime import date
from decimal import Decimal
from credit.shared.schedule import monthly_schedule

loan = monthly_schedule(Decimal("100000"), Decimal("0.12"), 12, date(2026, 2, 1))
print(loan.model_dump_json(indent=2))
```

Les formules, conventions et limites de calcul sont détaillées dans [FORMULES.md](FORMULES.md).

## Limites et prochaine étape

Usage local uniquement : ports liés à `127.0.0.1`, identités locales par jetons et
droits explicites par dossier. Pas de SSO, d’isolation forte entre institutions, de
sauvegarde gérée ni de chiffrement applicatif. Avant toute exposition externe : contrôle d'accès et
cloisonnement, TLS, secrets gérés, politique de conservation et sauvegardes testées,
limitation des requêtes et revue de sécurité. Ne pas importer de vrais dossiers dans
cet environnement de démonstration. Les journaux applicatifs ne contiennent ni corps
ni URL brute ; les traces financières restent dans l'historique métier en base.

Les noyaux financiers reçoivent toujours du JSON validé. Le module PDF est désormais
intégré en amont, avec originaux et résultats non vérifiés séparés : voir
[EXTRACTION_PDF.md](docs/EXTRACTION_PDF.md) pour l’installation OCR français, les lots
et les routes de documents. Pas de connexion bancaire, frontend, apprentissage ou
taux effectif réglementaire. Aucune ingestion de
transactions brutes : les agrégats de flux reconstitués doivent exclure les transferts
internes caisse/banque et les doubles mouvements avant import. Les champs inattendus
sont rejetés. Les deux modes entreprises n'impliquent pas de conversion automatique
d'une balance comptable en flux directs.

Les données de ménage et coûts professionnels doivent être correctement délimitées.
Les clés de périodes, flux directs, emplois financés et coûts nets nécessitent un
rapprochement documentaire humain. La validation ne détecte pas toutes les erreurs
de classification entre postes différents. Pas de simulation probabiliste ni de
projection automatique de croissance. La recommandation et la décision demeurent au
prêteur. L'étape suivante recommandée est une revue des contrats et rapprochements
sur des cas métier validés, avant de définir une grille de critères versionnée.

Le détail des vérifications réellement exécutées et de leurs résultats figure dans
[VALIDATION.md](VALIDATION.md). Les résultats par période ont des contrats distincts :
`net_retained_income`, `margin_after_credit`, `projected_reserve` pour les particuliers ;
`operating_receipts`, `cash_available_for_debt`, `closing_cash` pour les entreprises.

L’intégration PDF et ses vérifications sont décrites dans
[docs/EXTRACTION_PDF.md](docs/EXTRACTION_PDF.md) et
[docs/VALIDATION_PDF.md](docs/VALIDATION_PDF.md).
