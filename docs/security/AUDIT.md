# Audit sécurité et fiabilité — Crédit PME 0.5

Audit local du 4 novembre 2026. Périmètre : backend FastAPI, deux noyaux,
extraction PDF/images/OCR, politiques et simulations, éditions HTML/PDF,
SQLAlchemy/Alembic, Compose, registre de jetons et tests. Aucun frontend, SSO,
mot de passe, cookie de session, renouvellement JWT, modèle entraîné ou LLM
n’est présent. Aucun test offensif n’a visé un service extérieur. Les seules
requêtes externes concernent les paquets et avis de vulnérabilité publics.

Le travail non commité antérieur a été conservé. La référence de départ est
`181 passed` sur le backend et `167 tests OK` dans le module PDF. Les résultats
bruts, reproductions avant/après, inventaires et dumps synthétiques sont conservés
sous `output/security/`, hors Git. Le registre détaillé est `findings.json`.

## Modèle de menace

Données sensibles : identité, coordonnées, périmètre du ménage, données financières,
originaux et images dérivées, OCR, corrections, scores et rapports historiques.
Les identifiants UUID ne sont pas une autorisation.

```mermaid
flowchart LR
  C[Client non fiable] --> A[API : identité serveur, institution, permission et objet]
  A --> D[(PostgreSQL privé : dossiers, preuves, résultats, audit)]
  A --> W[Processus PDF / image / OCR borné]
  W --> A
  A --> F[Moteurs déterministes distincts]
  F --> D
  A --> P[Présentation filtrée demandeur / analyste]
  P --> R[Rendu HTML et PDF isolé]
  R --> D
```

Frontières : requêtes et fichiers non fiables, API authentifiée, stockage privé,
worker traitant du contenu hostile, calculs alimentés par contrats métier,
restitution filtrée. Un utilisateur authentifié peut tenter d’accéder à un autre
objet, forger une validation, écraser une version, provoquer des traitements coûteux
ou faire imprimer des données internes. Un PDF peut viser un parseur natif, contenir
du JavaScript, un fichier embarqué ou des références malveillantes. Le worker ne
constitue pas une preuve d’innocuité ; les ressources et droits restent bornés.

## Corrections principales

- La lecture d’un dossier par le demandeur retire réellement les observations
  internes. Les analyses brutes, règles, revues et événements internes exigent
  désormais une habilitation analyste, en plus des droits sur l’objet.
- Un JSON ne peut plus fabriquer `verified`, une revue, un run ou des références
  de source serveur. Les valeurs revues passent par le rattachement explicite
  existant. Les éditions demandeur restent projetées avant rendu.
- Classification réel/synthétique immuable après création. Création de données
  de démonstration réservée aux analystes ; mode démonstration interdit en production.
- Modification de dossier : `If-Match` obligatoire avec `version`, contrôle
  optimiste et verrou de dossier PostgreSQL sur les mutations. Les analyses
  utilisent un instantané cohérent ; les éditions précédentes restent figées.
- Revues sur extraction périmée refusées. Les corrections suivantes nécessitent
  `expected_review_revision`. La consommation de revues périmées est refusée.
- OCR réussi rejoué sur la même révision : même résultat, sans nouveau traitement.
  `Idempotency-Key` facultatif sur analyses détaillées et éditions : même ressource
  pour mêmes entrées ; 409 si les données ont changé. Une nouvelle clé génère une
  nouvelle analyse/édition. Ce mécanisme ne couvre pas toutes les anciennes routes.
- Jetons : expiration, désactivation et révocation vérifiées à chaque requête.
  Création atomique du registre et outils opérateur sans affichage des secrets.
  Un même jeton ne peut pas désigner deux identités/institutions : registre ambigu refusé.
- Bornes JSON, profondeur et complexité, montants/rates, quotas par acteur et
  dossier, pagination, limitations de requêtes, hôtes autorisés et erreurs épurées.
  Le chemin utilisé pour l’authentification provient du scope ASGI, pas d’une URL
  reconstruite depuis le Host. CORS reste fermé par défaut.
- Audit structuré séparé des données financières, avec acteur, institution,
  ressource, référence de requête, opération et résultat. Consultation institutionnelle
  réservée au responsable/administrateur. Les événements métier existants restent
  séparés. Les contenus financiers et les jetons ne sont pas journalisés.
- Worker OCR : environnement minimal sans DSN ni jetons hérités, groupe de processus
  arrêté au dépassement de durée, `no_new_privs`, core dumps interdits et réduction
  d’UID si un worker est lancé depuis root. Image applicative non root, racine
  en lecture seule, capacités retirées, mémoire/processus/tmp bornés.
- Annulation OCR : POST `/{core}/{case}/submissions/{id}/cancel`, après autorisation
  sur le dossier et la pièce. Le worker actif de ce processus est arrêté ; le résultat
  devient un échec explicite. Une opération d’un autre processus API n’est pas
  accessible par ce registre local ; une infrastructure distribuée n’a pas été ajoutée.
- Scanner ClamAV utilisé s’il est installé, sans exécution shell. Absence/échec
  explicitement signalés, jamais « sain ». `CREDIT_ANTIMALWARE_REQUIRED=true` bloque
  les dépôts en 503 si le scanner n’est pas disponible. Ici ClamAV est absent.
- Les espaces privés ignorés par Git sont aussi exclus de l’image Docker.

## Résultats financiers indépendants

| Contrôle | Résultat attendu et vérifié |
|---|---|
| Particulier : 500 000 − 300 000 − 50 000 − 80 000 | 70 000 FCFA |
| Même dossier, revenus −20 % | −30 000 FCFA |
| Entreprise : 4 000 000 − 3 000 000 | 1 000 000 disponibles pour la dette |
| Dette totale 250 000 + 400 000 | 650 000 FCFA |
| Marge entreprise | 350 000 FCFA |
| Couverture entreprise | 20 / 13, soit 1,538461538… |
| Charge essentielle hors total +10 000 | 60 000, identique sur les deux routes |

La normalisation des charges a été déplacée dans le domaine partagé et rendue
idempotente. Elle modifie une copie, jamais l’original. Les calculs fixent leur
contexte Decimal pour ne pas dépendre du thread appelant. Une dette sans échéancier
et au capital inconnu n’est plus assimilée à un service nul. Un encaissement reporté
dont la source est inconnue ne devient pas certain dans la période d’arrivée.
Les montants flottants JSON sont refusés : utiliser une chaîne décimale ou un entier
exact. Cela évite la perte silencieuse de centimes sur les grands montants.

La somme des poids, les absences de données, les périodes non applicables, les
déficits saisonniers, les retenues, le BFR et les garanties restent contrôlés.
Aucun modèle prédictif n’est installé : score combiné indisponible, aucune PD fabriquée.
Les règles illustratives restent explicitement non validées. Les calculs
arithmétiques testés ne constituent pas une validation métier bancaire.

## Dépendances et applicabilité

Audit `pip-audit 2.9.0`, sur l’inventaire des distributions installées du projet :
9 avis connus sur 3 paquets avant correction ; aucun avis connu sur cet inventaire
après mise à jour. Le module local n’est pas un paquet public interrogeable dans
cette base. Cette mesure ne couvre ni les vulnérabilités inconnues, ni toute l’image OS.

| Paquet | Avant → après | Applicabilité constatée |
|---|---|---|
| FastAPI | 0.115.12 → 0.162.0 | Compatibilité nécessaire pour la version de Starlette corrigée |
| Starlette | 0.46.2 → 1.3.1 | Reconstruction d’URL pertinente pour l’ancien middleware. Pas de `FileResponse`, `StaticFiles`, `request.form` ou `HTTPEndpoint` exposé dans ce backend : avis Range, formulaires et Windows non directement atteignables ici. Mise à jour malgré cela. |
| PyMuPDF | 1.26.6 → 1.26.7 | Avis d’écriture de fichier dans sa CLI d’extraction embarquée, non exposée par les routes ; parseur tout de même mis à jour. |
| pytest | 8.3.5 → 9.0.3 | Avis de répertoire temporaire sur hôte de tests partagé ; dépendance de développement uniquement. |

Deux avertissements de dépréciation des outils de test subsistent (httpx/TestClient
et AnyIO). La résolution est verrouillée dans `uv.lock` ; les tests PDF ont été
réexécutés avec les nouvelles versions.

La recherche de secrets cible les clés privées, jetons GitHub et identifiants AWS
dans les fichiers suivis et non ignorés. Aucune correspondance trouvée. Elle ne
prouve pas l’absence de tout secret possible. Les identifiants publics de Compose
restent exclusivement ceux de la démonstration locale, refusés par le garde de production.
Aucune rotation d’un secret réel n’a été effectuée.

## Exécution et configuration

```bash
uv sync --locked
.venv/bin/python -m pytest -q
(cd modules/credit_pme_pdf && ../../.venv/bin/python -m unittest discover -s tests -v)
.venv/bin/ruff check .
.venv/bin/python scripts/check_secrets.py
.venv/bin/python scripts/reproduce_audit_findings.py
```

Pour les tests PostgreSQL, utiliser uniquement une base dédiée, car les fixtures
suppriment leurs tables :

```bash
TEST_DATABASE_URL=postgresql+psycopg://credit:credit_local@127.0.0.1:5432/credit_test \
  .venv/bin/python -m pytest -q
```

Lancement local (aucun déploiement extérieur effectué) :

```bash
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -t workspace-api .
CREDIT_AUTH_JSON="$(cat .local/auth/users.json)" CREDIT_ALLOW_DEMO=true docker compose up -d --no-build
curl --fail http://127.0.0.1:8000/health
```

Sur machine sans proxy, `docker compose up --build -d` convient. La migration
`0006` ajoute le verrou de version et l’audit. Pour Python direct : exécuter
`alembic upgrade head` puis Uvicorn sur `127.0.0.1`, avec le registre privé configuré.

Mise à jour d’un dossier :

```http
PUT /individuals/DOSSIER
Authorization: Bearer <jeton>
If-Match: 3
Content-Type: application/json

<JSON du dossier>
```

Lire d’abord `version` dans le GET. Absence : 428 ; version périmée : 409.
`Idempotency-Key` sur les POST d’analyse détaillée et d’édition est une clé de
réessai facultative, maximale 128 caractères. Les anciennes routes ne bénéficient
pas toutes de cette déduplication : ne pas réessayer aveuglément une création.

Gestion locale des jetons (opérateur autorisé uniquement) :

```bash
.venv/bin/python scripts/init_local_auth.py --user analyste-exemple --role analyst --institution institution-exemple --hours 24
.venv/bin/python scripts/manage_local_auth.py revoke --user IDENTITE
.venv/bin/python scripts/manage_local_auth.py rotate --user IDENTITE --hours 24
```

Ces dernières commandes sont fournies comme procédure ; elles n’ont été essayées
que sur un registre temporaire synthétique. Le registre est modifié atomiquement,
les nouveaux jetons sont sauvegardés en fichiers privés sans affichage et les
changements sont journalisés sans jetons. Les anciens registres sans date restent
compatibles en mode local ; ils sont refusés pour l’authentification en production.

## Corrigé mais non entièrement vérifiable ici / risques restants

- Production non déployée. `compose.production.example.yaml` est un gabarit,
  pas une configuration bancaire validée. PostgreSQL `verify-full`, hôtes,
  registre privé, HTTPS et absence de démonstration sont obligatoires. L’entrée
  de production refuse un rôle PostgreSQL superuser/createdb/createrole/bypassrls
  et n’effectue pas les migrations avec le compte applicatif.
- TLS externe, certificats, chiffrement des volumes/sauvegardes, supervision et
  restauration d’un vrai environnement restent à configurer/vérifier. Le Compose
  local utilise volontairement un compte de développement privilégié et du trafic
  PostgreSQL local non TLS. Ne pas l’exposer.
- Pas de MFA ni SSO. Le registre opaque local ne suffit pas pour des comptes
  bancaires privilégiés en production : intégrer et tester un fournisseur approprié.
- Le worker non root avec limites n’est pas un sandbox complet du système de
  fichiers. Une compromission native reste un risque ; séparation par conteneur
  ou sandbox OS dédiée à éprouver avant exposition à des fichiers réels hostiles.
- Antivirus absent ici : les dépôts locaux restent `not_scanned`. L’image fournie
  n’ajoute pas de moteur ni de signatures antimalware ; en mode obligatoire, les
  dépôts restent bloqués tant qu’un scanner opérationnel n’est pas installé.
- Isolation institutionnelle applicative, pas de RLS PostgreSQL. Une compromission
  des identifiants DB peut dépasser cette frontière. Le rôle runtime restreint
  atténue les écritures, sans remplacer une stratégie d’isolation DB adaptée.
- Quotas et annulations par processus, pas de passerelle distribuée ni de quotas
  transactionnels globaux. Les limites de compte/pièces ne sont pas une facturation
  de stockage institutionnelle. Un déploiement multi-worker nécessite un mécanisme partagé.
- Audit local non inviolable : un administrateur DB/OS peut l’altérer. Prévoir un
  collecteur distant, conservation et supervision ; les contrôles d’accès ne sont
  pas une certification de non-répudiation.
- Pas de purge automatique des données financières : définir obligations et durées
  avec l’institution avant d’exécuter une rétention. Sauvegarde/restauration : voir
  `BACKUP_RESTORE.md` ; aucune donnée réelle n’a été supprimée pour cet audit.

Ces éléments empêchent de conclure que la plateforme est prête pour la production,
invulnérable ou certifiée. Les résultats bancaires et grilles doivent être approuvés
séparément de cette vérification logicielle.
