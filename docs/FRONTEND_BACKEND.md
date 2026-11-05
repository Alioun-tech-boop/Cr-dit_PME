# Connexion réelle du frontend et du backend

Les résultats réellement exécutés et limites sont consignés dans
[VALIDATION_FRONTEND_BACKEND.md](VALIDATION_FRONTEND_BACKEND.md).

Le frontend fourni est intégré dans `frontend/`. Ses quatre sources CSS, images,
menus, animations, centrage et aides sont conservés. Les commandes métier utilisent
les composants existants ; aucune formule financière n’est ajoutée au navigateur.
Le catalogue de politiques réellement appliqué vient de l’API authentifiée.

## Exécution locale — Linux, Python 3.12, Node 20 ou supérieur

Depuis la racine du dépôt :

```bash
uv sync --locked
[ -f .env ] || cp .env.example .env
cd frontend
npm ci
npm test
cd ..
docker compose up -d db
export DATABASE_URL=postgresql+psycopg://credit:credit_local@127.0.0.1:5432/credit
export CREDIT_AUTH_FILE="$PWD/.local/auth/users.json"
export CREDIT_WEB_ORIGIN=http://127.0.0.1:8000
uv run alembic upgrade head
```

Pour une **nouvelle** identité locale uniquement, le responsable choisit son rôle,
son institution et ses dossiers autorisés. Ne pas recréer une identité existante :

```bash
uv run python -m scripts.init_local_auth --user demandeur-web --institution institution-locale --role applicant --hours 168
uv run python -m scripts.provision_web_user --actor-id demandeur-web --username demandeur-web
```

La seconde commande demande deux fois le mot de passe, sans l’inscrire dans une
commande, un fichier public ou le frontend. Minimum 12 caractères. Elle peut
réinitialiser le mot de passe d’un accès navigateur existant et révoque ses sessions.
Le rôle et l’institution restent exclusivement dans le registre serveur.
`manage_local_auth.py` gère rotation, révocation et attribution explicite des dossiers.
Un analyste ne voit **pas** tous les dossiers de son institution par défaut.
Les identités techniques existantes restent utilisables, sans recopier leur Bearer
dans le navigateur. L’expiration de leur identité révoque aussi la connexion web.

```bash
# Installer Tesseract français si nécessaire (Debian/Ubuntu) :
# sudo apt-get install tesseract-ocr tesseract-ocr-fra
# Dans l'environnement de développement fourni, les modèles sont installés ici :
[ ! -d "$PWD/.local/share/tessdata" ] || export TESSDATA_PREFIX="$PWD/.local/share/tessdata"
tesseract --list-langs
uv run uvicorn credit.web.application:app --host 127.0.0.1 --port 8000 --no-access-log
```

Ouvrir **http://127.0.0.1:8000/**, menu → Profil → Se connecter.
Ne pas remplacer 127.0.0.1 par localhost sans modifier `CREDIT_WEB_ORIGIN` : la
comparaison d’origine CSRF est volontairement exacte. Aucun serveur Node séparé
n’est nécessaire. Les commandes purement techniques utilisant `credit.api:app`
restent disponibles ; elles ne servent pas le site et ne créent pas de session web.

### Docker, même origine

```bash
CREDIT_AUTH_JSON="$(cat .local/auth/users.json)" docker compose up --build -d
# Provisionnement interactif : le registre est passé côté serveur, jamais au navigateur.
docker compose exec api python -m scripts.provision_web_user --actor-id demandeur-web --username demandeur-web
```

L’application Docker applique la migration 0007 en mode local, sert le site et
l’API sur 8000. Les anciennes routes techniques Bearer à la racine sont conservées.
Swagger local : `/api/docs` ou `/docs`. L’API navigateur est sous `/api` et les
comptes sous `/auth`. Les volumes existants sont conservés ; ne pas utiliser `down -v`.
Si le registre a changé, recréer le conteneur avec le `CREDIT_AUTH_JSON` actualisé.
Pour un proxy avec autorité de certification particulière, suivre la commande de
construction `--secret id=proxy_ca` du README, sans désactiver TLS.

## Contrats réellement reliés

| Parcours | Routes et comportement |
|---|---|
| Connexion | `POST /auth/login` : identifiant/mot de passe Argon2id ; aucun rôle envoyé |
| Session/profil | `GET /auth/session`, `GET /auth/csrf`, `PATCH /auth/profile`, `POST /auth/logout` |
| Brouillon incomplet | `GET/POST /api/journeys`, `GET/PUT /api/journeys/{id}` ; propriétaire + institution, `If-Match` |
| Dossier métier | `POST /api/journeys/{id}/case` atomique et rapprochable après réponse perdue ; Pydantic et règles existantes |
| Dossiers autorisés | `GET /api/individuals`, `GET /api/businesses`, lectures et modifications existantes |
| Pièces/pages | Politiques serveur, submissions, sources, pages, confirmation, process et revue existants |
| Retrait avant confirmation | `POST .../submissions/{id}/withdraw` avec révision ; conservation de l’original et de la trace |
| Résultats | `GET /api/{core}/{id}/published-assessment` : rapport interne autorisé ou projection publiée demandeur |
| Calcul/simulation | Assessments et simulations existants, sans calcul JavaScript |
| PDF | Print editions existantes ; récupération authentifiée en Blob, sans URL publique ni jeton dans le lien |

Les listes de dossiers ont `limit` (1–100) et `offset`. L’interface affiche
actuellement au plus 100 dossiers autorisés par noyau. Les brouillons exposent
jusqu’à 100 éditions récentes par utilisateur ; une navigation de pagination
supplémentaire pourra être ajoutée pour des volumes plus élevés.

`submission.js` reste un adaptateur de compatibilité testé. Le parcours connecté
est orchestré par `backend-services.js` : sauvegarde persistante du brouillon,
finalisation atomique du dossier, envoi des sources et confirmation explicite.

### Reprise, conflits et incidents réseau

- « Enregistrer le brouillon » confirme une écriture serveur ; aucune sauvegarde
  automatique fictive. « Modifier les champs du dossier » permet de reprendre une demande transmise,
  tout en laissant les pièces confirmées verrouillées. Les champs incomplets sont autorisés dans le brouillon,
  jamais transformés en zéro ni injectés directement dans le noyau.
- Le dépôt nécessite un dossier métier validable. Les originaux reçus sont privés,
  les PDF multipages sont développés en pages éditables. Plusieurs images peuvent
  composer une pièce ; ajout, retrait, ordre, rotation et recadrage restent tracés.
- Un fichier seulement sélectionné et non reçu ne survit pas au rechargement :
  il faut le sélectionner à nouveau. Aucun document financier en localStorage.
- Les clés de création et d’upload sont conservées avant envoi. Empreintes et clés
  serveur permettent de rapprocher une réponse perdue sans réimporter l’original.
- Les conflits 409/428 ne sont pas écrasés. Pour un dossier, « Recharger les champs du serveur » remplace explicitement
  les champs locaux par le dossier métier courant ; pour une pièce, « Recharger les pages du serveur » remplace les
  modifications locales non enregistrées. Une pièce confirmée n’est plus éditable
  avant réouverture autorisée côté revue.
- La confirmation signifie réception et contrôle technique, jamais conformité,
  authenticité ou accord de crédit. Les avertissements qualité restent visibles.
- Si `fra` manque, le dépôt reste conservé et le traitement expose son blocage.
  Aucune substitution par `eng`.

### Revue, analyse et publication

L’analyste habilité traite la pièce puis ouvre ses pages, candidats, preuves et
coordonnées. L’éditeur de décisions de revue accepte le contrat serveur JSON :

```json
{"net_salary":{"value":{"amount":"500000","currency":"XOF","unit_multiplier":"1"},"evidence_ids":["identifiant-réel-retourné-par-le-moteur"],"reason":"Montant relu sur la page source"}}
```

Le nom du champ et les références doivent provenir de l’extraction courante ; cet
exemple ne constitue pas une valeur prédéfinie pour l’interface. Les sources et
corrections sont conservées. La revue n’authentifie pas la pièce.
Le rattachement aux calculs est un choix distinct de l’analyste, via une liste de
`review_id`, `field`, `target_path`, `expected_period`. Le serveur contrôle les
revues actuelles, périodes et unités ; aucun premier candidat n’est utilisé.

L’analyse est lancée en mode réel. Sans politique approuvée, pas de score inventé ;
sans modèle validé, pas de fusion 70/30. Les simulations travaillent sur une copie.
La publication est explicite par analyse : résultats financiers et/ou suggestions.
Le JSON destiné au demandeur ne contient ni sections internes, ni scores, ni règles,
ni preuves, ni observations internes. Retirer les deux autorisations sur la dernière
publication retire cette communication pour cette analyse. Les anciennes analyses
publiées peuvent rester consultables tant qu’elles ne sont pas retirées aussi.
La génération PDF et le partage à un partenaire restent des opérations distinctes.

## Sessions et sécurité

Cookie opaque HttpOnly, SameSite=Lax, Secure obligatoire en production ; empreinte
seule du secret de session en base. Durée absolue 8 heures, inactivité 30 minutes,
maximum 5 sessions actives ; nettoyage des sessions expirées à la connexion.
Le nonce CSRF vient d’un endpoint de même origine et reste en mémoire JavaScript.
Toutes les mutations par cookie vérifient nonce et Origin, y compris la déconnexion.
Une modification du registre d’identités révoque conservativement toutes les
sessions ; une modification de mot de passe ou désactivation révoque le compte.
Les anciennes routes racine exigent toujours un Bearer : elles n’acceptent pas
les cookies et ne permettent pas de contourner le CSRF de `/api`.

Les contrôles d’objets et d’institutions sont ceux du backend ; aucune option UI
ne permet de choisir un rôle. Les refus de connexion restent génériques et bornés.
Les événements ne contiennent pas les mots de passe ni les données financières.
Pas d’inscription publique, récupération de mot de passe, SSO ou MFA ajoutés :
le provisionnement et la réinitialisation passent par l’administration serveur.

## Hébergement existant

`frontend/.openai/hosting.json` décrit un hébergement **statique**. Il ne constitue
pas une passerelle API. Copier seulement `dist/` sur ce site ne suffit pas.
Deux options : servir le site avec cette application ASGI, ou configurer, sur le
même domaine HTTPS, les chemins `/api/*` et `/auth/*` vers elle. Un exemple Nginx
est fourni dans `deploy/nginx.same-origin.conf.example`.

Il reste à fournir l’origine de déploiement, un hébergement capable de cette
passerelle, le registre d’identités réel et la configuration TLS/proxy approuvée.
Aucune URL extérieure n’est injectée pour contourner la CSP. Le contrôle d’accès
au site hébergé reste indépendant de l’identité métier Crédit PME. Aucun
déploiement distant n’est effectué par cette intégration locale.

## Vérifications reproductibles

```bash
uv run pytest -q
uv run ruff check credit scripts tests migrations
(cd frontend && npm ci && npm test)
uv run python frontend/tests/verify_backend.py "$PWD"
(cd modules/credit_pme_pdf && ../../.venv/bin/python -m unittest discover -s tests -v)
# Chromium installé ; chemin configurable par CHROMIUM_PATH :
uv run python -m scripts.run_frontend_e2e
```

Le dernier script lance un serveur local isolé sur 8004, une base synthétique et
Chromium, puis arrête le serveur. Il conserve traces, captures, PDF et résultats
sous `output/frontend/browser-*/`, exclus de Git. Il ne modifie ni la base métier
ni les identités existantes. `CREDIT_E2E_PORT` permet de choisir un autre port.
Les fixtures de compte et mots de passe synthétiques sont uniquement des tests.

### Limite Docker observée dans cet environnement

La construction de l’image a réussi. Sa création de conteneur a ensuite échoué
avec `no space left on device` sur le disque de 7,9 Go de cette session (pilote
Docker vfs). Les caches de cette construction ont été nettoyés sans supprimer le
volume PostgreSQL. Le service et les parcours complets sont vérifiés avec Uvicorn
natif et PostgreSQL ; le démarrage de l’image doit être revalidé sur un hôte ayant
suffisamment d’espace. Cette limite ne doit pas être présentée comme un lancement
Compose réussi.
