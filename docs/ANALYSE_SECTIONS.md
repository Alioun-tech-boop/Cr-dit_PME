# Analyse explicable par sections — version 0.3

Les moteurs `IndividualAnalysisEngine` et `BusinessAnalysisEngine` réutilisent les
calculs déterministes existants. Les sept sections particuliers et neuf sections
entreprises sont indépendantes, testables sans HTTP ni base. Aucun frontend n’est
présent. La décision du prêteur reste un objet distinct, laissé vide.

## Lancement sous Linux / Python 3.12

Depuis la racine du dépôt :

```bash
uv sync --locked
# Seulement si cette identité n’existe pas encore :
.venv/bin/python scripts/init_local_auth.py --user agent-scans --reviewer
# PostgreSQL local persistant :
docker compose up -d db
export DATABASE_URL=postgresql+psycopg://credit:credit_local@127.0.0.1:5432/credit
export CREDIT_AUTH_FILE="$PWD/.local/auth/users.json"
export CREDIT_ALLOW_DEMO=true
# Si installé par scripts/install_pdf_ocr.sh dans cet environnement :
export TESSDATA_PREFIX="$PWD/.local/share/tessdata"
.venv/bin/alembic upgrade head
.venv/bin/uvicorn credit.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

Dans un second terminal :

```bash
.venv/bin/python examples/assessments/generate.py
.venv/bin/python scripts/demo_assessments.py
# Après arrêt / redémarrage du serveur, sans supprimer le volume PostgreSQL :
.venv/bin/python scripts/demo_assessments.py --verify-existing
```

Les quatre rapports JSON et Markdown de référence sont dans
`examples/assessments/`. Les réponses HTTP et identifiants conservés sont dans
`output/assessments/api/`, ignoré par Git. Ne jamais versionner les jetons locaux.
Le script n’utilise que les dossiers synthétiques fournis.

Alternative Compose :

```bash
CREDIT_AUTH_JSON="$(cat .local/auth/users.json)" CREDIT_ALLOW_DEMO=true docker compose up --build -d
```

Dans cet environnement cloud, fournir le certificat au build comme indiqué dans
le README. La démonstration est désactivée par défaut. Sans politique approuvée,
un dossier réel obtient des constats et calculs disponibles, sans score inventé.

## Routes et exemples

Toutes les routes ci-dessous exigent le jeton d’un agent autorisé au dossier.
La configuration curl privée est créée par `init_local_auth.py`.

```bash
curl --fail --config .local/auth/cda4d66fbf09672f.curl \
  -H 'Content-Type: application/json' \
  --data-binary @examples/assessments/individual_control.json \
  http://127.0.0.1:8000/individuals
```

Le nom de la configuration est le SHA256 tronqué du nom de l’agent : le script
`demo_assessments.py --user agent-scans` le retrouve automatiquement.
Après création, utiliser l’identifiant retourné à la place de `DOSSIER` :

```http
POST /individuals/DOSSIER/assessments
Content-Type: application/json
Authorization: Bearer <jeton>

{"mode":"demonstration","policy_id":"individuals-illustrative-v1"}
```

Pour une entreprise : `/businesses/DOSSIER/assessments` et politique
`businesses-illustrative-v1`. Pour un dossier réel sans grille : `{"mode":"real"}`.
Les routes `GET /individuals/DOSSIER/assessments` et équivalent entreprises listent
l’historique ; `GET /assessments/ANALYSE` restitue l’instantané et le résultat ;
`GET /assessments/ANALYSE/report` restitue le rapport français.

```http
POST /assessments/ANALYSE/simulations
Content-Type: application/json
Authorization: Bearer <jeton>

{"specification":{"kind":"stress","scenario":{"revenue_drop":"0.20"}}}
```

Autres spécifications : `{"kind":"lower_amount","principal":"192000"}`,
`{"kind":"extend_term","months":12}`, `calendar` avec échéancier explicite,
`existing_restructure` avec référence et preuves d’échéancier,
`startup_delay` avec nombre de périodes. Une durée dépassant l’horizon nécessite
`future_periods` explicites et `projection_assumptions`. Le moteur conserve le coût
calculable mais signale une simulation incomplète tant que ces projections manquent.
Un scénario de stress remplace le stress actif ; un changement de prêt le conserve.
Les données originales ne sont jamais modifiées.

## Formules, sources et limites

- Particulier : disponible = revenus personnels nets − dépenses essentielles ;
  marge = disponible − échéances existantes − nouvelles échéances.
- Entreprise : capacité dette = encaissements − sorties nécessaires hors dette ;
  marge = capacité − service total de dette ; trésorerie finale = initiale + marge
  + décaissement du financement − emplois financés. Le BFR est analysé séparément,
  sans nouvelle déduction dans les flux directs. Une garantie ne corrige pas un déficit.
- Service de dette : capital + intérêts + frais exigibles. Les retenues déjà
  déduites du salaire sont rapprochées ; un traitement ambigu bloque le calcul.
- Montants XOF en `Decimal`, arrondi monétaire `ROUND_HALF_UP` à deux décimales,
  sérialisés comme chaînes. Unités comptables 1, 1 000 ou 1 000 000 explicites avant
  calcul ; absence d’unité ou dénominateur nul = indicateur indisponible.
- Taux nominal annuel / 12 pour les seules mensualités constantes ; taux nul et
  ajustement du dernier remboursement couverts. Aucun taux effectif réglementaire.
- Les périodes observées et prévisionnelles sont distinctes. Pas de projection
  automatique d’une moyenne ; rapprochement des dates seulement si les flux datés
  sont déclarés complets et réconciliés. Les moyennes historiques ne valent pas
  promesse de revenus. Aucun transfert interne ne doit figurer dans les agrégats.

Chaque section conserve données, périodes, preuves, pages/coordonnées disponibles,
formules, règles, alertes, informations manquantes et suggestions. Les contradictions
exigent vérification sans qualification automatique de fraude. Une transcription
revue ne certifie jamais l’authenticité d’une pièce.

Les données OCR brutes non revues ne sont pas utilisables comme montants financiers.
`validated_sources` permet un rattachement explicite d’une valeur revue au champ
monétaire visé : `review_id`, `field`, `target_path`, `expected_period`. La revue doit
confirmer séparément la période ISO du document et un montant avec devise `XOF` et
`unit_multiplier: "1"`. Le serveur vérifie dossier, auteur, période et cible ; les
sources et transformations restent conservées. Les statuts simplement déclarés dans
un JSON ne constituent pas une authentification documentaire.

## Politiques, scores et modèles

Les politiques JSON sont dans `credit/assessment/policies/`, surcharge serveur par
`CREDIT_ANALYSIS_POLICIES_DIR`. Chaque grille contient critères, unités, champs
critiques, bandes, poids et limites du produit. Les exemples portent explicitement
`illustrative_not_validated` : uniquement dossiers synthétiques ET mode démonstration
activé. Une grille réelle exige `approved`, autorité, référence et date d’approbation ;
ce registre reste sous responsabilité de l’organisation.

Somme des poids = 1, pas de renormalisation si section requise manquante ou non
applicable. Un score de section incomplet reste absent. Score de solvabilité 0–100,
élevé favorable ; indice de risque = 100 − score, sans interprétation probabiliste.
Un déficit reste visible et impose une revue même si d’autres notes sont favorables.
Les suggestions n’impliquent ni accord ni réduction causalement prouvée du défaut.

Le modèle est actuellement `not_available`. Combinaison 70 % critères / 30 % modèle
seulement avec deux scores compatibles, validation et périmètre autorisés par la
politique. Une PD est un objet distinct nécessitant calibration, définition du défaut,
horizon et population. Perte attendue = PD × LGD × EAD seulement avec paramètres
justifiés et cohérents. Aucun modèle entraîné ou PD n’est livré.

Les suggestions chiffrent montant inférieur, mensualité et coût total lors d’un
allongement autorisé ; l’apport manquant n’est jamais supposé disponible. Aucun
conseil ne réduit arbitrairement les dépenses essentielles ou ne masque une dette.

## Historique et exploitation

Migration `0004_section_assessments` : nouvelles analyses séparées des anciens
calculs, instantanés JSON, empreintes d’entrée/résultat, politique complète, versions,
hypothèses, acteur, revues humaines et lien parent de simulation. Modifier le dossier
ne modifie pas l’analyse passée. Les droits existants sont vérifiés à chaque lecture.

Cette version reste locale : pas de frontend, de décision automatique, de grille
métier validée, de modèle prédictif, ni de conversion automatique de pièces en
comptabilité. Les limites de sécurité et d’authentification du README restent applicables.
