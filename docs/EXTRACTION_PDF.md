> Guide historique v0.1. Depuis v0.2, les dépôts suivent [PARCOURS_SCANS.md](PARCOURS_SCANS.md), avec identité et confirmation des pages. Le POST direct décrit ci-dessous retourne 410.

# Extraction PDF intégrée — Debian 13 / Python 3.12.14

Le module fourni a été installé dans `modules/credit_pme_pdf/`. Ses trois documents
ont été lus avant intégration : [README](../modules/credit_pme_pdf/README.md),
[INTEGRATION](../modules/credit_pme_pdf/docs/INTEGRATION.md),
[TEST_REPORT d'origine](../modules/credit_pme_pdf/docs/TEST_REPORT.md).
Le rapport d'origine décrit l'environnement de fabrication de l'archive ; les
vérifications de cette intégration figurent dans [VALIDATION_PDF.md](VALIDATION_PDF.md).

## Installation effectuée et reproductibilité

Un seul environnement virtuel : `/workspace/.venv`, géré par `uv`. L'installation
ajoute le paquet local et ses dépendances à `pyproject.toml` et `uv.lock`. Les versions
FastAPI, Pydantic, SQLAlchemy, Alembic, psycopg et uvicorn restent inchangées. Les versions
PyMuPDF 1.26.6, pdfplumber 0.11.9 et ReportLab 4.4.9 correspondent à celles du module.
Aucun `pip install` global ni modification des paquets système n'a été effectué.

Depuis ce dépôt :

```bash
cd /workspace
UV_CACHE_DIR=/tmp/credit-uv uv sync --locked
scripts/install_pdf_ocr.sh
export TESSDATA_PREFIX=/workspace/.local/share/tessdata
tesseract --list-langs
```

Tesseract était déjà installé ; le modèle `fra` a été installé dans `.local/share/tessdata`,
avec les configurations TSV et des liens vers `eng` et `osd` du système. Le script
contrôle l'empreinte SHA-256 du modèle officiel `tessdata_fast/4.1.0/fra.traineddata` :
`ced037562e8c80c13122dece28dd477d399af80911a28791a66a63ac1e3445ca`.
L'export est nécessaire dans chaque terminal de lancement Python. Le modèle français
n'est pas remplacé par l'anglais. Si Tesseract lui-même manque sur une autre Debian :
`sudo apt-get install tesseract-ocr tesseract-ocr-fra` ; avec cette installation système,
l'export local n'est pas nécessaire.

Les dossiers `output/` et `.local/` sont exclus du suivi Git et du contexte Docker.
Les JSON produits contiennent les données du PDF : les protéger comme les originaux.
Seuls des PDF synthétiques ont été utilisés ici.

## Lancer le module et extraire un PDF personnel

Depuis `/workspace`, avec `TESSDATA_PREFIX` exporté :

```bash
.venv/bin/python -m credit_pdf catalog --output output/pdf/catalog.json
.venv/bin/python -m credit_pdf extract modules/credit_pme_pdf/examples/pdf/payslip_detail.pdf \
  --type payslip --ocr never --output output/pdf/payslip_detail.json
.venv/bin/python -m credit_pdf extract "/chemin/vers/mon_document.pdf" \
  --type payslip --ocr auto --lang fra --output output/pdf/mon_document.json
.venv/bin/python -m json.tool output/pdf/mon_document.json
```

Remplacer le chemin personnel et choisir un type dans le catalogue. La CLI n'attache
pas sa sortie à un dossier. Un PDF chiffré peut être traité localement avec
`--password-prompt` ; l'API intégrée ne reçoit pas de mots de passe PDF.

## Traiter un lot

```bash
.venv/bin/python -m credit_pdf batch modules/credit_pme_pdf/examples/manifest.json \
  --ocr never --output-dir output/pdf/batch
.venv/bin/python -m json.tool output/pdf/batch/manifest_results.json
```

Pour un lot personnel, créer un manifeste JSON dont les chemins sont relatifs au
manifeste, puis remplacer son chemin dans la commande et utiliser `--ocr auto --lang fra` :

```json
{"documents":[{"path":"pieces/bulletin.pdf","document_type":"payslip"}]}
```

Chaque fichier possède son JSON et son statut. Un échec n'arrête pas les autres
pièces ; la CLI retourne le code 1 si au moins une pièce échoue. Les 132 exemples
natifs sont traités sans OCR pour isoler la lecture native.

## Lancer l'API intégrée

Docker Compose installe désormais Tesseract et `fra` dans l'image, puis applique
les migrations, dont `0002_pdf_documents`. Aucun chemin OCR de l'hôte n'est transmis
au conteneur. Le volume PostgreSQL existant est conservé.

```bash
cd /workspace
docker compose up --build -d
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/documents/catalog
```

Dans cet environnement cloud avec certificat du proxy :

```bash
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -t workspace-api .
docker compose up -d --no-build
```

Alternative Python (ne pas utiliser le même port que le conteneur API) :

```bash
export TESSDATA_PREFIX=/workspace/.local/share/tessdata
export DATABASE_URL=postgresql+psycopg://credit:credit_local@127.0.0.1:5432/credit
.venv/bin/alembic upgrade head
.venv/bin/uvicorn credit.api:app --host 127.0.0.1 --port 8001 --no-access-log
```

Swagger présente les contrats à `/docs`. L'API importe directement
`credit_pdf.engine.extract_pdf` ; aucun serveur intermédiaire n'est requis.
Le serveur autonome du module reste disponible pour diagnostic avec
`.venv/bin/python -m credit_pdf serve --port 8765`. Son jeton facultatif
`CREDIT_PDF_API_TOKEN` ne protège que ce serveur autonome, pas le backend.

## Envoyer une pièce et consulter son résultat

Créer d'abord le dossier ou reprendre explicitement son identifiant existant :

```bash
curl --fail -X POST http://127.0.0.1:8000/individuals \
  -H 'Content-Type: application/json' --data-binary @examples/salarie.json
```

Remplacer `ID_DOSSIER` et `ID_DOCUMENT` ci-dessous par les identifiants retournés :

```bash
curl --fail -X POST \
  'http://127.0.0.1:8000/individuals/ID_DOSSIER/documents?document_type=payslip&role=justificatif_revenu&period=2026-10-01&ocr=auto' \
  -H 'Content-Type: application/pdf' \
  --data-binary @modules/credit_pme_pdf/examples/pdf/payslip_scan.pdf \
  --output output/pdf/api-result.json
curl --fail http://127.0.0.1:8000/individuals/ID_DOSSIER/documents
curl --fail http://127.0.0.1:8000/individuals/ID_DOSSIER/documents/ID_DOCUMENT \
  --output output/pdf/api-read.json
.venv/bin/python -m json.tool output/pdf/api-result.json
```

Pour une entreprise, utiliser `/businesses/ID_DOSSIER/documents` et le type explicite
approprié, par exemple `balance_sheet`. Les documents transversaux comme un relevé
ne déterminent jamais eux-mêmes leur dossier. Aucun rattachement par nom ressemblant.
`period` est la période visée **déclarée par l'appelant**, pas une période validée depuis
le PDF ; `role` est le rôle déclaré de la pièce. Des exercices différents restent
présents dans le résultat brut, sans choix automatique d'une colonne.

| Opération | Route / comportement |
|---|---|
| Catalogue des 132 profils | `GET /documents/catalog` |
| Envoi PDF binaire, type/rôle/période obligatoires | `POST /individuals/{id}/documents` ou `/businesses/{id}/documents` |
| Liste des pièces rattachées | `GET /{noyau}/{id}/documents` |
| Résultat brut et métadonnées | `GET /{noyau}/{id}/documents/{document_id}` |
| Type MIME incorrect | 415 |
| Corps vide, taille déclarée incorrecte | 400 |
| Plus de 25 Mio ou 100 pages | 413 |
| Type inconnu, PDF invalide/chiffré, paramètres invalides | 422 |
| Dossier absent ou pièce d'un autre dossier/noyau | 404 |
| Deux extractions déjà en cours dans ce processus | 429 et `Retry-After: 5` |
| Erreur interne | 500, message générique sans contenu documentaire |

La limite de 25 Mio est vérifiée sur l'en-tête puis pendant la lecture du flux,
y compris sans `Content-Length`. Le traitement PDF est déporté dans le pool de
threads de FastAPI pour ne pas bloquer la boucle HTTP. Ce n'est pas une isolation
mémoire/CPU de production et il n'existe pas de délai global par document.

## Persistance, séparation et accès

La table `documents` conserve le PDF original en binaire, l'empreinte SHA-256, le
noyau et l'identifiant du dossier, type/rôle/période déclarés, date de collecte et
résultat brut complet. Les versions, pages, rectangles, textes sources et
avertissements du module sont conservés sans réécriture. Les lectures n'exposent
pas les octets de l'original ; ceux-ci restent dans PostgreSQL. Une nouvelle
extraction crée une nouvelle pièce, sans dédoublonnage ni écrasement.

Le statut reste `extracted_unverified`, `review_status=pending` et
`ready_for_scoring=false`. L'envoi ne modifie pas le dossier financier, ses preuves
saisies, les analyses historiques, un score ou un jeu d'entraînement. Aucun premier
candidat n'est choisi. La revue et l'adaptateur de valeurs vérifiées vers les noyaux
restent une étape future distincte. Les avertissements OCR ou d'échelle ne sont
jamais masqués ; un succès HTTP ne signifie ni authenticité ni données complètes.

Le backend existant n'a pas d'authentification ni de droits par utilisateur ou
institution : les nouvelles routes conservent cette limite et le même accès aux
dossiers. Le contrôle de rattachement empêche une consultation sous un autre dossier,
mais ne constitue pas une autorisation entre utilisateurs. Ports liés à localhost,
usage synthétique local exclusivement. Le stockage est privé au service via les
identifiants PostgreSQL de démonstration ; aucun chiffrement applicatif ni politique
de suppression n'est ajouté. Avant des pièces réelles ou une exposition extérieure :
identité et droits sur les dossiers, protection/chiffrement du stockage, conservation
et isolation du traitement sont nécessaires. Aucun contenu PDF n'est journalisé par
l'intégration ; utiliser `--no-access-log` comme documenté pour éviter les URL brutes.

## Réexécuter les vérifications

Commande du module, **depuis son dossier**, avec le Python virtuel du backend :

```bash
cd /workspace
source .venv/bin/activate
export TESSDATA_PREFIX=/workspace/.local/share/tessdata
cd modules/credit_pme_pdf
python -m unittest discover -s tests -v
cd /workspace
python -m pytest -q
python -m ruff check .
```

Les tests HTTP utilisent des sockets/primitives locales : dans le bac à sable,
les permissions réseau sont nécessaires. Pour PostgreSQL, utiliser uniquement
la base dédiée jetable `credit_test` (les migrations y sont annulées par les tests) :

```bash
TEST_DATABASE_URL=postgresql+psycopg://credit:credit_local@127.0.0.1:5432/credit_test \
  .venv/bin/python -m pytest -q
```

Après avoir produit les cinq sorties dans `output/pdf/` et le lot selon les commandes
du module, `python scripts/verify_pdf_examples.py` vérifie montants, sources de page,
colonnes annuelles, champs interactifs et avertissements, puis écrit
`output/pdf/verification.json`. Les noms attendus sont `payslip_detail.json`,
`bank_table.json`, `balance_multiyear.json`, `form.json`, `payslip_scan_fra.json`.

Pour reproduire le contrôle HTTP synthétique, sans utiliser de documents personnels :

```bash
.venv/bin/python scripts/demo_pdf_api.py
docker compose restart db api
.venv/bin/python scripts/demo_pdf_api.py --verify-existing
```

Le premier appel crée deux dossiers de démonstration et cinq pièces ; il sauvegarde
leur état dans `output/pdf/api/state.json`. La seconde commande Python compare les
résultats persistés, dossiers et analyses à cet état, après disponibilité de `/health`.
