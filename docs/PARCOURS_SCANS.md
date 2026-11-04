# Dépôt et revue des pièces numérisées — API v0.2

Ce parcours utilise directement `credit_pdf.engine.extract_pdf` et `apply_review` du
module fourni. Les calculs Particuliers et Entreprises restent inchangés. Le dépôt,
la qualité, l'OCR, la revue de transcription et l'authenticité sont des états distincts.
Aucun état ne déclenche un score, un entraînement ou une décision de crédit.

## Installation sur ce projet Debian 13 / Python 3.12

```bash
cd /workspace
UV_CACHE_DIR=/tmp/credit-uv uv sync --locked
scripts/install_pdf_ocr.sh
export TESSDATA_PREFIX=/workspace/.local/share/tessdata
```

Tesseract et `fra` sont nécessaires à la lecture des scans. Le script installe le
modèle français localement, conserve les configurations TSV et vérifie son empreinte.
Sans `fra`, le dépôt et les originaux sont conservés ; `/process` retourne
`processing_status=waiting_dependency`, `ocr_status=waiting_dependency`, `fra_missing`.
Réinstaller la dépendance puis rappeler `/process`. Aucune substitution par `eng`.
Les textes natifs et tableaux natifs sont conservés : pas de rasterisation générale.

## Identité et droits

Le projet n'avait ni frontend, ni annuaire d'utilisateurs, ni queue de tâches.
Une identité locale par jeton a donc été ajoutée. La configuration privée contient
uniquement les empreintes SHA-256 des jetons, les identifiants d'agents, leurs
habilitations et les dossiers explicitement partagés. Les jetons en clair restent
côté client dans des fichiers de mode 600, exclus de Git et des images Docker.

Une seule fois, créer une identité de démonstration :

```bash
.venv/bin/python scripts/init_local_auth.py --user agent-scans --reviewer
```

Cette commande refuse d'écraser une identité existante. Dans l'environnement livré,
`agent-scans` est déjà configuré. Le jeton n'est jamais affiché. Le fichier client
est `.local/auth/cda4d66fbf09672f.json`, et son équivalent curl
`.local/auth/cda4d66fbf09672f.curl`. Utiliser le chemin imprimé par le script pour
un autre nom d'agent. Le rôle `--native-exception` est une habilitation **optionnelle**
qui autorise des dérogations justifiées ; il ne certifie pas les pièces.

Les nouveaux dossiers appartiennent à l'identité authentifiée qui les crée.
`case_ids` dans `.local/auth/users.json` accorde explicitement l'accès à d'autres
dossiers ; `--grant-case ID` le fait lors de la création d'une nouvelle identité.
Les anciens dossiers sans propriétaire ne sont attribués à personne automatiquement :
leur identifiant doit être ajouté explicitement à cette liste. Aucun droit global
implicite. Les accès refusés à un dossier, ses pièces, ses pages ou ses analyses
retournent 404 pour ne pas révéler leur existence. Sans jeton : 401 ; sans identité
configurée : 503. `/health` et la documentation des schémas restent publics.

La configuration locale n'est pas un SSO de production : pas d'expiration de jeton,
de MFA ni d'administration web. L'agent de revue provient du jeton contrôlé par le
serveur, jamais d'un champ `reviewer` envoyé par le navigateur.

## Lancer les services

Docker conserve la base et applique les migrations, dont `0003_scan_workflow`.
Le modèle français est installé dans l'image ; ne pas lui transmettre le chemin
`TESSDATA_PREFIX` de l'hôte. La configuration d'identités envoyée à Docker contient
des empreintes, **pas les jetons en clair** :

```bash
CREDIT_AUTH_JSON="$(cat .local/auth/users.json)" docker compose up --build -d
curl --fail http://127.0.0.1:8000/health
```

Dans l'environnement cloud, monter le certificat de confiance du proxy au build :

```bash
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -t workspace-api .
CREDIT_AUTH_JSON="$(cat .local/auth/users.json)" docker compose up -d --no-build
```

Un changement d'identités Docker nécessite de recréer l'API avec la nouvelle valeur :
`CREDIT_AUTH_JSON="$(cat .local/auth/users.json)" docker compose up -d --force-recreate api`.
Ne pas publier le résultat de `docker inspect`, qui contient cette configuration.
Aucun fichier privé de l'hôte n'est monté dans le conteneur, ce qui évite les problèmes
de permissions du Docker rootless de cet environnement.

Alternative Python, avec relecture du fichier d'identités à chaque requête :

```bash
export CREDIT_AUTH_FILE=/workspace/.local/auth/users.json
export TESSDATA_PREFIX=/workspace/.local/share/tessdata
export DATABASE_URL=postgresql+psycopg://credit:credit_local@127.0.0.1:5432/credit
docker compose up -d db
.venv/bin/alembic upgrade head
.venv/bin/uvicorn credit.api:app --host 127.0.0.1 --port 8001 --no-access-log
```

Swagger `/docs` possède le bouton **Authorize** pour un jeton Bearer. Les ports
restent liés à localhost. Il n'existe pas de frontend ni de demande de caméra.
Une future interface pourra proposer l'import et, après action explicite, la caméra.

## Politiques documentaires

`GET /documents/policies` retourne les 132 règles, leurs profils, formats et limites.
Le référentiel `credit/documents/policies.v1.json` est indépendant des calculs
financiers. Incrémenter sa version lorsqu'une règle évolue. Chaque dépôt conserve
la règle, les limites et la configuration qualité qui lui ont été appliquées.
Les règles sont relues à la création des dépôts Python ; les plafonds du pool de
processus sont fixés au démarrage et bornent aussi les anciens dépôts. Redémarrer
l'application pour changer ces plafonds. En Docker, reconstruire l'image si les
fichiers de politique embarqués ont changé.

| Politique | Identifiants réels principaux du catalogue |
|---|---|
| `scan_required` — identité | `identity_card`, `passport` |
| Domicile et baux | `address_proof`, `residential_lease`, `commercial_lease`, `occupancy_title` |
| Revenus, emploi, pension | `payslip`, `pension_statement`, `employment_certificate`, `employment_contract`, `employment_appointment` |
| Juridique et exercice | `rccm`, `ifu`, `operating_license`, `articles`, `appointment`, `power_of_attorney`, `borrowing_resolution`, `ownership` |
| Dette et remboursement | `loan_contract`, `loan_balance`, `payment_receipt` |
| Commerce signé | `customer_contract`, `service_contract`, `purchase_order`, `awarded_market` |
| Fiscal/social | `tax_clearance`, `tax_payment`, `social_payment`, `social_return` |
| Propriété, garanties, caution | `property_title`, `vehicle_registration`, `equipment_ownership`, `stock_pledge`, `receivable_assignment`, `encumbrance_report`, `land_use`, `guarantee_letter`, `guarantor_commitment` |
| Autorisations signées | `data_authorization`, `bic_consent` et délégations ci-dessus |
| `original_preferred` | `bank_statement`, `mobile_money_statement`, états financiers (`annual_financials`, `balance_sheet`, etc.), `amortization_schedule`, `sales_invoice`, `purchase_invoice`, `quotation`, `proforma_invoice` |
| `structured_required` | `credit_application`, `partner_application`, `income_expense_declaration`, `household_budget`, `household_business_split`, `business_description`, `financial_forecast`, `cash_forecast`, `project_budget`, tous les `historical_*` |

Le catalogue n'a pas de profil dédié à chaque attestation sociale : le profil proche
et le rôle déclaré doivent être vérifiés par l'agent. Les autres identifiants sont
explicitement configurés, généralement en `original_preferred`. Les règles fiscales,
sociales et de signature sont des choix du produit, modifiables et sans prétention
à créer une obligation réglementaire. Les profils Particuliers/Entreprises sont
contrôlés côté serveur, sans router une pièce sur la seule ressemblance de noms.

Pour `scan_required`, un PDF natif ou un petit logo accompagné de texte ne suffit
pas. Une page mixte est acceptée si la couverture d'images atteint le seuil technique
configuré (initialement 30 %), avec contrôle qualité et revue. Une page image dominante
avec texte OCR reste acceptée. Une exception de PDF natif exige une identité habilitée
et `exception_reason` non vide et détaillée lors de la création ; acteur, motif et date
sont enregistrés. La dérogation ne contourne aucune limite technique.

**La présence d'images ne prouve pas une numérisation papier. Un PDF rasterisé peut
être indiscernable d'un scan.** La classification est une heuristique technique,
jamais une vérification d'authenticité. Le backend ne rasterise pas un PDF natif pour
le faire passer sous `scan_required`. Les rendus PNG servent à la prévisualisation
et aux mesures de qualité, sans changer cette décision prise sur l'original.

## Parcours API

Le corps d'un envoi de source est le fichier binaire, sans formulaire multipart.
L'extension et le MIME annoncé ne déterminent pas son format : il est décodé dans
le worker. Seuls JPEG, PNG et PDF sont admis. Les images animées, fichiers corrompus
et PDF chiffrés sont refusés explicitement dans ce parcours.

Remplacer les identifiants par ceux retournés. Exemple pour le service Docker :

```bash
export CREDIT_CURL_CONFIG=/workspace/.local/auth/cda4d66fbf09672f.curl
curl --config "$CREDIT_CURL_CONFIG" --fail http://127.0.0.1:8000/documents/policies
curl --config "$CREDIT_CURL_CONFIG" --fail -X POST http://127.0.0.1:8000/individuals \
  -H 'Content-Type: application/json' --data-binary @examples/salarie.json
curl --config "$CREDIT_CURL_CONFIG" --fail -X POST http://127.0.0.1:8000/individuals/CASE/submissions \
  -H 'Content-Type: application/json' \
  -d '{"document_type":"payslip","role":"revenu_personnel","period":"2026-10-01"}'
curl --config "$CREDIT_CURL_CONFIG" --fail -X POST http://127.0.0.1:8000/individuals/CASE/submissions/PIECE/sources \
  -H 'Content-Type: image/jpeg' --data-binary @examples/scans/salary.jpg
```

Répéter `/sources` pour ajouter des photographies à **cette même pièce et ce même
client**, ou envoyer un PDF multipage en une fois. Chaque page reçoit un identifiant
stable. Le format réel, le nombre de pages et leurs mesures sont retournés.

`PUT /pages` reçoit la liste complète des pages conservées, dans l'ordre voulu :
omettre une page la retire du brouillon, sans supprimer l'original. Une liste vide
est autorisée ; la confirmation exige au moins une page. Le contrôle de révision
évite d'écraser une modification concurrente.

```json
{
  "expected_revision": 3,
  "pages": [
    {"id":"PAGE_B","rotation":90,"crop":[0.02,0.05,0.98,0.95]},
    {"id":"PAGE_A","rotation":0,"crop":[0,0,1,1]}
  ]
}
```

Rotation horaire : 0/90/180/270 degrés. Le recadrage est `[gauche,haut,droite,bas]`,
normalisé entre 0 et 1 **dans la page source avant la rotation demandée**. Une image
EXIF est normalisée de manière traçable ; l'original n'est jamais modifié.

| Opération, avec préfixe `/{noyau}/{case_id}/submissions/{id}` | Méthode / suffixe |
|---|---|
| Créer / lister | POST / GET `/{noyau}/{case_id}/submissions` |
| Lire états et pages | GET préfixe |
| Ajouter un JPEG, PNG ou PDF | POST `/sources` |
| Télécharger l'original autorisé | GET `/sources/{source_id}` |
| Modifier ordre, rotation, recadrage ou retirer des pages | PUT `/pages` |
| Prévisualiser une page du brouillon | GET `/pages/{page_id}/image` |
| Confirmer et contrôler les dérivés | POST `/confirm` |
| Exécuter l'OCR français et l'extraction | POST `/process` |
| Consulter un résultat immuable | GET `/runs/{run_id}` |
| Voir une page de ce résultat | GET `/runs/{run_id}/pages/{page_id}` |
| Enregistrer une correction | POST `/runs/{run_id}/reviews` |
| Historique des actions | GET `/events` |
| Réouvrir une nouvelle révision | POST `/reopen` |

`{noyau}` vaut `individuals` ou `businesses`. La confirmation refuse les pages
bloquées ; elle conserve un dérivé de préparation. Les avertissements seuls ne
bloquent pas une pièce lisible. L'OCR est un appel synchrone borné, avec état `running`
commité avant son lancement : un autre appel peut lire les états pendant le traitement.
Il n'y a pas de file distribuée. Après un redémarrage interrompant une opération,
le traitement peut être relancé après la durée limite plus 10 secondes ; pas de
modification de pages pendant un traitement actif.

`structured_required` utilise d'abord `POST /{noyau}/{case_id}/structured-inputs` :

```json
{
  "document_type":"credit_application",
  "period":"2026-10-01",
  "fields":{"requested_amount":null,"purpose":"Equipement déclaré","duration":"12 mois"}
}
```

Les clés nécessaires sont déclarées dans `required_fields` du référentiel.
`null` est une donnée explicitement inconnue, conservée dans `missing_values`, pas
un zéro. Les valeurs restent déclarées et non vérifiées. Une saisie n'est pas encore
un dossier financier validé : les contrats des noyaux restent obligatoires avant
calcul. Pour joindre un justificatif, créer un dépôt avec son `supporting_structured_id`.
La pièce ne renseigne jamais automatiquement le champ encore inconnu.

## Qualité, erreurs et limites

`quality.v1.json` contient les paramètres techniques initiaux **à calibrer**, pas
une norme bancaire : variance du Laplacien sur vignette 256 px (flou), contraste,
luminance/exposition, fraction d'encre, contenu proche des bords, dimensions et
orientation suggérée par OSD. Les DPI déclarés des images et les DPI estimés des
images incorporées au PDF sont restitués lorsqu'ils existent. Un rendu de PDF n'est
pas une mesure certaine de sa résolution d'acquisition.

Pages vides/uniformes ou de dimensions infimes : blocage à la confirmation.
Faible résolution, flou, faible contraste, exposition, orientation et proximité des
bords : avertissements à contrôler, sans déclaration certaine de coupure. Les
empreintes détectent des doublons exacts de fichiers/rendus, pas tous les doublons
visuels. Elles ne prouvent pas l'identité de deux originaux physiques.

Plafonds initiaux : 25 Mio/fichier, 100 Mio d'originaux par dépôt, 50 pages, 20 millions
de pixels par image ou rendu OCR prévu, 2 workers et 2 réceptions simultanées par
instance. Lecture HTTP et worker : 90 secondes chacun. Worker Linux : 768 Mio
d'espace d'adressage, CPU limité et fichiers temporaires plafonnés à 128 Mio.
Un groupe de processus expiré, y compris Tesseract, est tué ; les fichiers temporaires
sont placés sous le répertoire privé du parent et nettoyés. Les originaux restent en base.

Les plafonds s'appliquent aussi aux PDF, à leurs images incorporées, aux corps sans
`Content-Length` et au cumul des sources. Le nombre de workers doit être multiplié
par le nombre d'instances si l'application est répliquée ; cette version s'exécute
avec un seul processus Uvicorn.

Erreurs : 400 corps vide/incomplet, 408 réception expirée, 413 limite dépassée,
422 format/politique/qualité invalide, 429 capacité occupée, 409 révision ou état
incompatible. Une panne OCR conserve les sources et expose un état d'attente ou
échec ; un HTTP 200 sur `/process` exige donc aussi la lecture des états retournés.

## Revue et provenance

Chaque résultat contient les lignes, tableaux et champs candidats du module,
leurs valeurs brutes, pages et coordonnées. La clé `source` ajoute l'identifiant
et l'empreinte de l'original, sa page et la matrice `processing_to_source`.
Les PDF utilisent les points de page non tournée, relatifs au cropbox source ;
les images utilisent les pixels de l'original avant EXIF. Les conversions EXIF,
recadrage et rotation sont conservées. Les coordonnées d'une correction doivent
correspondre à la **version de traitement** affichée, pas à un brouillon plus récent.

Exemple de correction, avec une preuve réellement présente dans le résultat :

```json
{
  "decisions": {
    "net_income": {
      "value":{"amount":"280000","currency":"XOF","unit_multiplier":"1"},
      "evidence_ids":["p1:l6"],
      "reason":"Montant lu sur la zone source et transcription contrôlée"
    }
  }
}
```

Si le champ est manquant, l'agent peut désigner une zone manuelle, sans fabriquer
une sortie OCR : ajouter `regions:[{"id":"manual:zone1","page_id":"PAGE", "bbox":[10,10,80,30]}]`
et utiliser `evidence_ids:["manual:zone1"]`. Les coordonnées sont les points de la
page dérivée affichée. Le serveur contrôle les limites de la zone et enregistre
sa correspondance source. Le motif de correction, l'agent authentifié et la date
sont conservés. La valeur brute et les anciens résultats ne sont jamais écrasés.

La revue reste `partially_reviewed` : elle valide des transcriptions désignées et
ne signifie ni complétude métier ni authenticité. `authenticity_status=not_assessed`
et `ready_for_scoring=false` restent inchangés. Aucun premier candidat, même unique,
n'est transféré dans les noyaux financiers ou dans des exemples d'entraînement.

## Stockage, compatibilité et vérifications

Originaux binaires, empreintes, inspections, dérivés, résultats, revues et événements
sont conservés dans PostgreSQL (SQLite temporaire pour les tests). Tous les accès aux
pages/originaux sont contrôlés. Les sources supprimées du brouillon restent disponibles
aux agents autorisés pour l'audit. Aucune route ne modifie un original ou un ancien run.

L'ancien `POST /{noyau}/{id}/documents` retourne désormais **410** et ne permet pas
de contourner le parcours ; ses lectures historiques restent disponibles et protégées.
Le CLI autonome du module peut toujours extraire un PDF, mais ne crée ni dépôt
accepté ni valeur utilisable dans le backend. Les guides v0.1 restent historiques.

```bash
.venv/bin/python examples/scans/generate.py
.venv/bin/python scripts/demo_scans.py --user agent-scans
CREDIT_AUTH_JSON="$(cat .local/auth/users.json)" docker compose restart db api
.venv/bin/python scripts/demo_scans.py --user agent-scans --verify-existing
```

Les résultats JSON, images de comparaison et états du démonstrateur sont dans
`output/scans/api/`, exclu de Git. Pour le serveur Python, ajouter `--base-url http://127.0.0.1:8001`.

```bash
TESSDATA_PREFIX=/workspace/.local/share/tessdata .venv/bin/python -m pytest -q
TEST_DATABASE_URL=postgresql+psycopg://credit:credit_local@127.0.0.1:5432/credit_test \
  TESSDATA_PREFIX=/workspace/.local/share/tessdata .venv/bin/python -m pytest -q
cd modules/credit_pme_pdf
TESSDATA_PREFIX=/workspace/.local/share/tessdata ../../.venv/bin/python -m unittest discover -s tests -v
```

La base `credit_test` est dédiée et jetable : les tests y annulent les migrations.
Voir [VALIDATION_SCANS.md](VALIDATION_SCANS.md) pour les exécutions réelles.

Limites : données synthétiques uniquement, pas de mesure terrain de qualité ou
précision OCR, pas de vérification de signatures ni de complétude physique certaine,
pas de sauvegarde gérée ou suppression réglementaire. L'isolation par processus et
limites de ressources n'est pas un sandbox de sécurité OS : un déploiement externe
nécessite notamment identité de production, isolation de privilèges, TLS, protection
du stockage et politique de conservation. Aucun frontend n'a été créé puisque le
projet n'en possède pas.
