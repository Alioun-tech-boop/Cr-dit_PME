# Documents imprimables — Crédit PME 0.4

Les éditions utilisent les champs réellement disponibles, les instantanés d’analyse
et les valeurs documentaires explicitement revues et rattachées par le parcours
existant. Aucun score, ratio, résultat ou engagement n’est inventé dans le rendu.
Il n’existe pas de frontend dans ce dépôt : cette livraison fournit l’API,
Swagger, l’aperçu HTML imprimable et les exemples, sans interface supplémentaire.

## Installation et lancement Linux

Python 3.12, PostgreSQL 16.6, versions verrouillées dans `uv.lock`.
ReportLab 4.4.9, déjà utilisé pour les tests, devient une dépendance d’exécution.
Ses polices Vera intégrées fournissent les caractères français sans téléchargement
au moment du rendu. Aucun navigateur ni serveur de rendu externe n’est nécessaire.

```bash
uv sync --locked
# Seulement si l’agent n’existe pas encore :
.venv/bin/python scripts/init_local_auth.py --user agent-scans --reviewer
# Pour une nouvelle institution : utiliser --institution IDENTIFIANT_STABLE
# Le même identifiant doit être attribué aux agents de cette institution.
docker compose up -d db
export DATABASE_URL=postgresql+psycopg://credit:credit_local@127.0.0.1:5432/credit
export CREDIT_AUTH_FILE="$PWD/.local/auth/users.json"
export CREDIT_ALLOW_DEMO=true
.venv/bin/alembic upgrade head
.venv/bin/uvicorn credit.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

Alternative Docker, avec registre d’identités privé existant :

```bash
CREDIT_AUTH_JSON="$(cat .local/auth/users.json)" CREDIT_ALLOW_DEMO=true docker compose up --build -d
```

Dans cet environnement cloud, construire avec le CA du proxy :

```bash
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -t workspace-api .
CREDIT_AUTH_JSON="$(cat .local/auth/users.json)" CREDIT_ALLOW_DEMO=true docker compose up -d --no-build
```

Le nom d’image Compose dépend du répertoire ; ici `workspace-api`.
Le mode démonstration reste limité aux dossiers synthétiques et peut être désactivé.
La migration `0005` ajoute les éditions et l’institution sans modifier les anciens PDF.

## Essai reproductible

Dans un second terminal, depuis la racine :

```bash
.venv/bin/python examples/printing/generate.py
.venv/bin/python scripts/demo_printing.py
# Après un redémarrage de l’API, sans supprimer la base :
.venv/bin/python scripts/demo_printing.py --verify-existing
```

Neuf PDF et neuf HTML synthétiques sont livrés dans `examples/printing/`.
Le script HTTP crée quatre dossiers, leurs analyses et dix-sept éditions ; il
vérifie les empreintes et l’absence de modification des dossiers. Ses résultats
privés sont dans `output/printing/api/` (hors Git). `--base-url` permet un autre port.

Ouvrir un HTML d’exemple dans le navigateur, puis utiliser **Imprimer / Ctrl+P**.
Aucun téléchargement ni impression n’est déclenché automatiquement. Le PDF donne
la pagination garantie ; celle de l’impression HTML dépend du navigateur. Les
styles A4, marges, retours de ligne et en-têtes de tableaux sont partagés au niveau
du modèle de présentation, avec mise en page adaptée à chaque moteur de rendu.

## Catalogue

`GET /individuals/DOSSIER/print/templates`, ou `/businesses/DOSSIER/print/templates`.

| Identifiant | Particulier | Entreprise / PME |
|---|---|---|
| identification | Identité et coordonnées | Entreprise et représentants |
| credit_request | Demande de crédit | Demande de financement |
| income_expenses | Revenus et charges | Non applicable |
| household_budget | Budget du ménage | Non applicable |
| activity | Non applicable | Présentation de l’activité |
| financial_declaration | Non applicable | Déclaration financière issue des champs saisis |
| cashflows | Non applicable | Encaissements et décaissements |
| debts | Dettes et engagements | Dettes et échéances |
| working_capital | Non applicable | Créances, fournisseurs et stocks |
| project_budget | Non applicable | Projet et plan de financement |
| documents | Pièces déposées et demandes connues | Idem |
| complete_file | Dossier complet | Dossier complet |
| analysis_summary | Synthèse | Synthèse |
| analysis_report | Analyse détaillée | Analyse détaillée |
| simulation_report | Simulation historisée | Simulation historisée |
| improvement_plan | Suggestions, sans engagement | Suggestions, sans engagement |

La liste des pièces manquantes reprend les demandes réellement enregistrées.
Pour une activité à flux reconstitués sans comptes structurés, la déclaration
financière présente les flux disponibles sans inventer un compte de résultat.
Elle n’ajoute pas d’obligations réglementaires. Les formulaires inconnus ou
inapplicables sont refusés. Sans analyse, les rapports autorisés restent des
brouillons explicites ; une simulation nécessite un identifiant de simulation.

## Prévisualiser, générer et télécharger

Tous les appels exigent le jeton configuré et les droits sur le dossier.
Le fichier curl ci-dessous correspond à l’identité d’exemple `agent-scans` ;
`init_local_auth.py` indique le chemin réel pour une autre identité.

```bash
# Créer un dossier synthétique ; relever son id dans la réponse.
curl --fail --config .local/auth/cda4d66fbf09672f.curl \
  -H 'Content-Type: application/json' \
  --data-binary @examples/printing/individual_complete.json \
  http://127.0.0.1:8000/individuals

# Éléments manquants AVANT génération :
curl --fail --config .local/auth/cda4d66fbf09672f.curl \
  -H 'Content-Type: application/json' \
  -d '{"template_id":"complete_file","audience":"applicant"}' \
  http://127.0.0.1:8000/individuals/DOSSIER/print/preflight

# Aperçu HTML, sans émission d’une version :
curl --fail --config .local/auth/cda4d66fbf09672f.curl \
  -H 'Content-Type: application/json' \
  -d '{"template_id":"complete_file","audience":"applicant"}' \
  http://127.0.0.1:8000/individuals/DOSSIER/print/preview -o output/aperçu.html

# Émission ; relever l’id d’édition :
curl --fail --config .local/auth/cda4d66fbf09672f.curl \
  -H 'Content-Type: application/json' \
  -d '{"template_id":"complete_file","audience":"applicant"}' \
  http://127.0.0.1:8000/individuals/DOSSIER/print/editions

curl --fail --config .local/auth/cda4d66fbf09672f.curl \
  http://127.0.0.1:8000/print-editions/EDITION/pdf -o output/dossier.pdf
```

Pour le rapport analytique : même POST avec
`{"template_id":"analysis_report","audience":"analyst","assessment_id":"ANALYSE"}`.
Pour la simulation : `simulation_report` et identifiant de l’analyse de simulation.
Les autres types utilisent la même structure. Swagger : `/docs`.

| Opération | Route |
|---|---|
| Précontrôle des champs | POST `/{core}/{case}/print/preflight` |
| Aperçu non émis | POST `/{core}/{case}/print/preview` |
| Émettre une version | POST `/{core}/{case}/print/editions` |
| Historique, dernière version par modèle et par analyse | GET `/{core}/{case}/print/editions` |
| État et empreintes | GET `/print-editions/{id}` |
| Modèle filtré transmis au rendu | GET `/print-editions/{id}/model` |
| Aperçu figé | GET `/print-editions/{id}/preview` |
| Télécharger le PDF | GET `/print-editions/{id}/pdf` |
| Journal interne | GET `/print-editions/{id}/events` |
| Lancer une édition en attente | POST `/print-editions/{id}/process` |
| Lier une pièce retournée distincte | POST `/print-editions/{id}/returned-documents` |

`core` vaut `individuals` ou `businesses`. Avec `generate_now:false`, l’édition est
stockée en `pending` ; le POST `process` exécute la génération. Sinon le POST attend
le worker local, puis restitue `completed` ou `failed`. L’état intermédiaire est
`processing`. Un échec ne fournit aucun PDF ; une nouvelle édition est nécessaire.
Il n’y a pas de file distribuée. Après arrêt brutal d’un processus en cours,
l’édition peut rester `processing` : examen technique puis nouvelle édition,
jamais marquage automatique comme terminée.

## Deux niveaux et communication explicite

- `applicant` : informations déclarées du demandeur ; aucune source interne,
  règle, grille, score ou observation interne dans le modèle envoyé au renderer.
- `analyst` : nécessite le droit `reviewer`, en plus du droit sur le dossier.
  Contient règles, sources, scores réellement disponibles et historique des
  transcriptions validées rattachées à l’analyse.

Par défaut, aucun résultat d’analyse n’est communiqué au demandeur. Un analyste
habilité peut enregistrer :

```http
POST /assessments/ANALYSE/print-publication
Authorization: Bearer <jeton analyste>
Content-Type: application/json

{"financial_results":true,"suggestions":true,"justification":"Communication des constats au demandeur après revue"}
```

Cette autorisation est historisée avec auteur/date. Une nouvelle édition demandeur
peut alors contenir les résultats financiers sélectionnés et les suggestions dont
le destinataire est `demandeur`. Les scores et observations internes restent exclus.
L’autorisation concerne cette analyse précise, pas toutes les analyses du dossier.
Elle ne partage ni n’envoie aucun fichier. Les éditions antérieures restent figées.

Les identités peuvent porter `institution_id`. Le serveur attribue cette institution
à la création du dossier et refuse les accès inter-institutions, même avec un
identifiant de dossier dans les droits d’un autre agent. Les anciens dossiers et
agents sans institution restent dans le périmètre local `null`. Leur attribution à
une institution existante nécessite une migration administrative explicite.
Ce registre local n’est pas un SSO ni une architecture de production multi-banque.

## Données et traçabilité

Le champ facultatif `record_details` des deux noyaux accepte adresse, téléphone,
courriel, référence d’identité, forme juridique, RCCM, IFU, représentants,
commentaire du demandeur et observations internes. Aucune valeur absente n’est
inventée. Les champs des calculs existants restent inchangés.

Un rapport avec `assessment_id` utilise exclusivement l’instantané de cette analyse,
pas les champs actuels du dossier. Les données OCR sont celles explicitement
validées et liées par `validated_sources` du moteur d’analyse. Aucun premier candidat
OCR n’est sélectionné par le service d’impression. Les valeurs non revues gardent
leur statut « Extrait non contrôlé ». Une revue de transcription n’authentifie pas
le document ; une signature imprimée n’est jamais créée.

Les inconnus, zéros, estimations, non-applicables, unités comptables, périodes et
prévisions sont conservés. Les décimaux sont seulement formatés pour l’affichage
avec l’arrondi du noyau. Aucun score n’est recalculé. Un dossier incomplet porte
« Brouillon » ou « Analyse incomplète ». Une politique de démonstration porte
« ILLUSTRATIF — NON VALIDÉ », quel que soit son score.

Chaque édition conserve en base privée : instantané et SHA256 d’entrée, analyse et
empreinte, modèle de présentation filtré, langue, auteur/date, versions, autorisation
de communication utilisée, HTML et PDF figés, empreintes et journal des événements.
Modifier le dossier ne change pas une édition existante. La dernière édition peut
être en échec : consulter aussi son état avant téléchargement.

Pour un retour signé, déposer la pièce par le parcours de scans, puis appeler
`returned-documents` avec `submission_id` et `description`. L’original émis reste
inchangé ; aucun statut d’authenticité ou signature certifiée n’est attribué.

## Configuration et limites

Variables documentées dans `.env.example` et transmises par Compose :

| Variable | Valeur initiale |
|---|---|
| CREDIT_PRINT_PLATFORM_NAME | Crédit PME |
| CREDIT_PRINT_LOGO_FILE | vide |
| CREDIT_PRINT_TIMEOUT_SECONDS | 30 |
| CREDIT_PRINT_CONCURRENCY | 2 par processus API |
| CREDIT_PRINT_MAX_PAGES | 120 |
| CREDIT_PRINT_MAX_INPUT_BYTES | 3 000 000 |
| CREDIT_PRINT_MAX_OUTPUT_BYTES | 15 000 000 |
| CREDIT_PRINT_MEMORY_MB | 512 par worker |

Le logo est uniquement un chemin configuré par l’administrateur, PNG/JPEG décodable,
moins de 500 Ko et un million de pixels. Il est converti en PNG contrôlé puis figé
avec l’édition. Aucune URL utilisateur n’est chargée. En Docker, fournir ce fichier
via une ressource contrôlée de l’image ou un montage administrateur en lecture seule,
puis configurer son chemin intérieur. Aucun logo bancaire ni cachet n’est fourni.

Le worker éphémère Linux impose CPU, mémoire, taille, nombre de pages et durée ;
les appels réseau sont refusés. Les gabarits échappent tout texte ; les seules
ressources du renderer sont les polices embarquées et le logo validé. Les routes
HTML ont une CSP restrictive, sans JavaScript, et les réponses privées `no-store`.
Les originaux ne sont pas publiés : téléchargements authentifiés, sans URL publique
ni lien de partage. Pas de chiffrement applicatif ni de signature électronique ;
conserver les limites d’exploitation locale décrites dans le README.

## Vérifications

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/python scripts/inspect_printing.py
```

Le dernier script vérifie texte, pagination et bornes des blocs, puis prépare les
images page par page dans `output/printing/visual/`. Il ne remplace pas la revue
visuelle humaine ; les vérifications exécutées sont dans `VALIDATION_PRINTING.md`.
