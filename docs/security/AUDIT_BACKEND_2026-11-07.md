# Audit complet du backend — Crédit PME

**Date :** 7 novembre 2026  
**Version auditée :** 0.5.0 (`pyproject.toml`)  
**Périmètre :** code Python `credit/`, migrations Alembic, tests, scripts d’exploitation, configuration de déploiement, documentation de sécurité.  
**Méthode :** revue statique intégrale du code et des tests, confrontation aux documents `README.md`, `VALIDATION.md`, `docs/security/AUDIT.md`, `docs/security/findings.json` et aux rapports de validation.  
**Limite d’exécution :** la suite de tests n’a pas été exécutée dans cet environnement Windows (Python 3.15, dépendances absentes, projet déclaré pour Python 3.12–3.13 et fortement lié à POSIX). Les conclusions sont donc des constats de code, non des résultats d’exécution.

---

## 1. Synthèse exécutive

Le backend est un **prototype avancé, cohérent et sérieusement documenté**, avec une vraie exigence de traçabilité, de déterminisme financier et de contrôle d’accès. Les points les plus solides sont :

- deux noyaux métier déterministes (`individuals`, `businesses`) et deux moteurs d’analyse (`assessment` v1, `financial_v2`), sans modèle ML ni LLM ;
- une arithmétique `Decimal` encadrée, des montants flottants refusés, une propagation explicite des inconnues ;
- une autorisation par objet et par institution, un filtrage réel des charges utiles avant sérialisation, et une protection contre l’assignation de champs internes ;
- un verrouillage optimiste généralisé (`version_id_col`, `If-Match`, révisions, clés d’idempotence) ;
- une chaîne documentaire isolée (worker, limites, OCR, antimalware optionnel, PDF actifs non exécutés) ;
- une signature Ed25519 détachée, un trousseau à états, une vérification publique minimale et une invalidation automatique des revues/attestations à toute modification du dossier ;
- un durcissement de déploiement réel (conteneur non root, racine en lecture seule, capacités retirées, `no-new-privileges`, garde de production).

En revanche, **le backend n’est pas prêt pour une mise en production bancaire réelle**. Les blocages ne sont pas principalement des bugs de calcul : ils portent sur l’exploitation, la sécurité d’infrastructure et la gouvernance des données. Les plus importants sont :

1. **Le script de droits PostgreSQL `ops/runtime_grants.sql` est incomplet** par rapport aux migrations 0007–0010 : il ne couvre ni les sessions web, ni les parcours partenaire/institution, et n’accorde pas `DELETE` sur `web_sessions`. Suivre la procédure documentée casse la connexion web et les parcours bancaires.
2. **`CREDIT_ENV` n’est pas validé** : une faute de frappe (`prod`, `Production`, espace final) désactive silencieusement les gardes de production (HTTPS, cookie `Secure`, interdiction de la démo, permissions du registre, docs).
3. **L’antimalware n’est pas obligatoire dans le garde de production** ; seul le gabarit Compose le force. Un déploiement hors gabarit peut accepter des fichiers `not_scanned`.
4. **Pas de MFA/SSO, pas de RLS PostgreSQL, pas de chiffrement au repos applicatif, pas de rétention/purge** : ces limites sont déjà reconnues dans `docs/security/AUDIT.md`, mais elles restent des bloqueurs.
5. **L’isolation des parseurs reste une isolation de processus**, pas un bac à sable OS ; les clés de signature sont montées dans le même environnement que l’API/worker partenaire.
6. **L’audit est synchrone et en base à chaque requête** : couplage disponibilité/audit, écritures amplifiées et croissance non bornée.
7. **Les limites de débit et de concurrence sont par processus**, sans store partagé : un déploiement multi-worker ou multi-instance multiplie les quotas.
8. **Le stockage des PDF et pièces est en `LargeBinary` dans PostgreSQL**, sans politique de conservation : volume, sauvegardes et coût croissent sans borne.

**Verdict :** utilisable pour une démonstration locale, des essais synthétiques et une revue métier ; **non homologable ni exposable à des données réelles** en l’état. La priorité n’est pas de réécrire les moteurs financiers, mais de corriger l’exploitation (droits SQL, configuration, sandbox, audit, rétention) et de faire valider les hypothèses métier et la grille de score par les instances compétentes.

---

## 2. Cartographie de l’architecture

### 2.1 Deux applications ASGI

| Application | Point d’entrée | Authentification | Usage |
|---|---|---|---|
| API technique | `credit.api:app` (`create_app`) | Bearer opaque, registre serveur | Clients techniques, scripts, tests, routes historiques |
| Application web | `credit.web.application:app` (`create_web_app`) | Cookie de session opaque + CSRF | Frontend statique, `/api`, `/auth` |

`create_web_app()` construit d’abord l’API via `create_app()`, puis monte l’API sous `/api` et sert `frontend/dist` à la racine. Les anciennes routes techniques (`/individuals`, `/businesses`, `/assessments`, `/documents`, `/print-editions`, `/security`, `/docs`…) sont redirigées vers l’API et **exigent toujours un Bearer** ; elles n’acceptent pas le cookie de session. C’est une décision de sécurité importante : le cookie de navigation ne peut pas contourner le CSRF des routes `/api`.

### 2.2 Couches

```
HTTP / ASGI
  ├─ credit.web.application      sessions, CSRF, CSP, frontend, /api
  └─ credit.api                  Bearer, limites, audit, routes métier
       ├─ credit.auth            authentification + autorisation d’objet
       ├─ credit.security.*      Limiter, audit, garde production, workers, fichiers
       ├─ credit.documents/*     dépôt, OCR, pages, revues, isolation
       ├─ credit.assessment/*    moteur v1 par sections, scoring explicable
       ├─ credit.financial_v2/*  moteur v2, scénarios, diagnostics, financement
       ├─ credit.printing/*      éditions HTML/PDF, présentation, isolation
       ├─ credit.partners/*      revue interne, attestation, paquet, outbox, banque
       └─ credit.institutions/*  consoles établissement, comptes, décisions, offres
```

### 2.3 Modules métier

- `credit/individuals/` : contrats, moteur, résultats, sections pour salariés, retraités, indépendants.
- `credit/businesses/` : contrats, moteur, résultats, sections pour comptabilité structurée ou flux reconstitués.
- `credit/shared/` : contrats communs, arithmétique, normalisation, résultats, échéanciers, scoring.
- `credit/application.py` : orchestration, instantanés, historique.
- `credit/persistence.py` : modèles SQLAlchemy et fabrique de sessions.
- `migrations/versions/0001…0010` : schéma additif, index, contraintes, versions optimistes.
- `modules/credit_pme_pdf/` : extraction PDF/OCR, catalogue documentaire, moteur PDF.
- `tests/` : 16 fichiers, suites backend et scénarios d’abus.
- `scripts/` : démonstration, provisionnement, clés, worker outbox, sauvegarde/restauration, vérifications.
- `deploy/`, `compose*.yaml`, `Dockerfile`, `render.yaml` : déploiement local et gabarits.

### 2.4 Dépendances principales

FastAPI 0.162.0, Starlette 1.3.1, Pydantic 2.11.4, SQLAlchemy 2.0.40, Alembic 1.15.2, psycopg 3.2.9, argon2-cffi 25.1.0, cryptography 50.0.2, Pillow 13.0.0, reportlab 4.4.9 ; Python `>=3.12,<3.14`. Les versions sont verrouillées dans `uv.lock`, avec contraintes PyMuPDF/pdfplumber.

---

## 3. Flux métier de bout en bout

### 3.1 Création et lecture d’un dossier

1. `POST /individuals` ou `POST /businesses` valide le JSON par le contrat Pydantic du noyau (`extra="forbid"`).
2. `client_fields()` refuse les champs réservés au personnel : observations internes, identité contrôlée, apport vérifié, preuves marquées `verified`, références de revue/source, classification synthétique pour un demandeur.
3. Le dossier est stocké dans `cases.payload` (JSON), avec `owner_id`, `institution_id`, `kind` et `lock_version`.
4. `GET /{core}/{id}` renvoie `public_payload()` : le personnel voit tout ; un demandeur ne voit ni `record_details.internal_observations` ni `analysis_details.identity`.
5. `PUT /{core}/{id}` exige `If-Match` avec la version courante (428 si absent, 409 si périmé). La classification du dossier est immuable.

### 3.2 Dépôt documentaire

1. `POST /{core}/{id}/submissions` crée un dépôt (`SubmissionRecord`) selon le catalogue et la politique documentaire.
2. `POST .../submissions/{sid}/sources` téléverse un original (image ou PDF), avec limite de taille, décodage sur le contenu réel et non sur le MIME déclaré.
3. L’inspection classe les pages (`native_text`, `mixed`, `image_dominant`, `empty_or_unusable`) et applique les règles : scan requis, original préféré, structuré requis, exception numérique autorisée et tracée.
4. `PUT .../pages` permet ordre, rotation, recadrage, suppression de pages blanches ; une révision est exigée.
5. `POST .../confirm` fige la réception technique ; `POST .../process` lance l’OCR/extraction dans un worker isolé.
6. Les résultats d’extraction restent des **candidats non vérifiés**. `POST .../runs/{run}/reviews` enregistre une revue humaine avec preuves, historique et révision attendue.
7. Le rattachement au calcul est un acte distinct (`validated_sources` avec `review_id`, `field`, `target_path`, `expected_period`) ; le serveur vérifie que la revue est courante, la période et l’unité.

### 3.3 Analyse financière

- **Moteur v1 (`assessment`)** : analyse par sections, politique explicite, suggestions, simulations, rapport. Version `section-analysis-1.1.0`.
- **Moteur v2 (`financial_v2`)** : calculs, sous-analyses, scénarios, tests inverses, diagnostics, variantes de financement. Version `financial_analysis_v2`.
- **Noyaux historiques** : `individuals` et `businesses` restent appelables directement et produisent des instantanés complets.
- Toute analyse est persistée dans `analyses` ou `assessments` avec entrée, résultat, configuration, preuves, version moteur et date. Une modification du dossier ne modifie jamais un instantané historique.
- Les routes d’analyse, de simulation et d’historique interne sont réservées au personnel (`enforce()`), et l’accès à l’objet est vérifié séparément.

### 3.4 Revue interne et attestation

1. Un analyste ouvre une revue (`POST /{core}/{id}/internal-reviews`) avec `Idempotency-Key` et `expected_case_version`.
2. La revue fige : version du dossier, instantané d’analyse, validations documentaires courantes, empreinte du périmètre documentaire, version de politique.
3. Un ou plusieurs signataires approuvent (`/internal-reviews/{id}/decisions`) avec révision attendue, motif et réserves communicables. Le demandeur ne peut jamais s’auto-approuver.
4. L’attestation (`/internal-reviews/{id}/attestation`) signe le manifeste approuvé, les données de l’attestation et l’empreinte du PDF en Ed25519.
5. Toute modification ultérieure du dossier, d’une pièce, d’une extraction, d’une donnée structurée ou d’une revue documentaire passe les revues en `superseded` et les attestations en `replaced` via le listener `before_flush` de `credit/partners/invalidation.py`.

### 3.5 Choix bancaire, consentement et transmission

1. Le demandeur prépare un paquet (`POST /{core}/{id}/banking/previews`) en sélectionnant des fichiers du manifeste approuvé, pour un partenaire actif et compatible.
2. Le serveur vérifie les catégories autorisées/requises, l’état de l’attestation, la fraîcheur de la revue, la version du partenaire et l’absence d’une autre transmission active.
3. La confirmation (`/transmissions/{id}/confirm`) exige le manifeste, l’attestation, la version de consentement, `accepted=true`, une déclaration de pouvoir et une révision attendue. La confirmation et la création de l’outbox sont dans la même transaction.
4. Le worker (`scripts/partner_worker.py`) ou le déclenchement manuel (`/dispatch`) réclame la ligne, vérifie à nouveau l’autorisation, les empreintes, la politique, la banque et l’attestation, puis appelle le connecteur.
5. Un simple accusé technique ne vaut pas accord ; seul un agent bancaire peut produire `received`.

### 3.6 Réception bancaire, compléments, décision et offre

1. La banque voit le paquet dans `/bank/inbox`, vérifie l’intégrité (`/verify`), télécharge l’archive privée, puis accuse réception ou demande des compléments.
2. Le demandeur dépose des compléments et doit confirmer séparément leur partage ; un dépôt seul ne les rend pas visibles.
3. Une décision bancaire (`/bank/transmissions/{id}/decision`) est immuable, idempotente, avec motif public, conditions, aperçu d’offre et empreinte.
4. Une offre formelle ou un décaissement exige une référence externe et une pièce jointe ; le décaissement ne peut suivre qu’une offre formelle.
5. Les décisions produisent un message dans la boîte client (`/inbox`) et, pour une offre, un PDF signé ou explicitement non signé, avec vérification publique minimale.

### 3.7 États principaux

| Objet | États |
|---|---|
| Revue | `internal_review`, `second_validation`, `needs_completion`, `approved`, `not_approved`, `superseded` |
| Attestation | `valid`, `expired`, `revoked`, `replaced` |
| Transmission | `ready`, `pending`, `sending`, `transmitted`, `received`, `under_review`, `additional_information`, `decision_available`, `failed`, `cancelled`, `withdrawn` |
| Décision bancaire | `favorable_opinion`, `conditional_offer`, `formal_offer`, `refused`, `disbursement_confirmed` |

---

## 4. Modèle de données et persistance

### 4.1 Tables

**Cœur métier :** `cases`, `analyses`, `assessments`, `submissions`, `documents`, `document_sources`, `document_runs`, `document_events`, `structured_inputs`, `document_reviews`, `print_editions`, `print_events`, `print_publications`, `security_events`.

**Web :** `web_users`, `web_sessions`, `web_registrations`, `journey_drafts`.

**Partenaires :** `case_grants`, `institution_workflow_policies`, `bank_partners`, `internal_reviews`, `partner_packet_files`, `internal_attestations`, `bank_transmissions`, `partner_outbox`, `partner_events`, `bank_attachments`.

**Institutions :** `institution_accounts`, `bank_decision_records`, `client_inbox_messages`.

### 4.2 Stockage JSON et contrats

- Les dossiers, analyses, revues, transmissions et décisions utilisent massivement des colonnes `JSON`. Les contrats Pydantic valident l’entrée, mais **le contenu JSON stocké n’est pas versionné** (`schema_version` absent sur `cases.payload`). Une évolution de contrat peut rendre d’anciens dossiers illisibles ou nécessiter une migration de données non outillée.
- Les instantanés d’analyse sont immuables et conservent la version du moteur, ce qui protège l’historique.
- Les champs inattendus sont rejetés (`extra="forbid"`), ce qui bloque l’assignation de champs internes par JSON.

### 4.3 Verrouillage optimiste et idempotence

- `version_id_col` sur `CaseRecord`, `SubmissionRecord`, `PrintEdition`, `WebUser`, `JourneyDraft`, `Partner`, `InternalReview`, `Attestation`, `Transmission`, `Outbox`, `InstitutionAccount`.
- `If-Match` obligatoire pour les modifications de dossier (428/409), révisions attendues pour les revues, confirmations et événements bancaires.
- Clés d’idempotence sur les analyses détaillées, éditions, revues, préparations, confirmations, événements, compléments.
- `StaleDataError` est converti en 409.
- Les anciennes routes de création ne sont pas idempotentes : un POST répété crée une nouvelle ressource.

### 4.4 Fichiers binaires

Les originaux, dérivés, paquets, pièces jointes bancaires et PDF de décision sont stockés en `LargeBinary` dans PostgreSQL (`DocumentRecord.original_pdf`, `PacketFile.payload`, `BankAttachment.payload`, `BankDecisionRecord.payload`). Les colonnes lourdes sont parfois `deferred`, mais elles restent dans la base et donc dans les sauvegardes.

Conséquences : croissance du volume, sauvegardes lourdes, temps de restauration, coût de stockage, difficulté de mise en œuvre d’une rétention sélective. Aucune purge automatique n’est active.

### 4.5 Migrations

Les migrations sont additives et versionnées de 0001 à 0010. Le test `test_release_migration_head` vérifie que la tête est `0010`. Les index couvrent les clés étrangères et les recherches fréquentes. Les contraintes d’unicité protègent les clés d’opération (`uq_review_operation`, etc.).

**Point d’attention :** les droits runtime documentés n’ont pas suivi les migrations 0007–0010 (voir AUD-01).

### 4.6 Invalidation

`credit/partners/invalidation.py` écoute `before_flush` et invalide les revues/attestations à toute modification du dossier. C’est une excellente défense contre la réutilisation d’une validation devenue obsolète. Le mécanisme est conservateur : l’empreinte couvre toutes les pièces du dossier, pas seulement celles partagées.

---

## 5. Moteurs financiers et calculs

### 5.1 Déterminisme

- Aucun modèle ML, aucun LLM, aucun appel réseau dans les calculs.
- `localcontext` avec précision 28, `ROUND_HALF_UP`, pièges `InvalidOperation`, `DivisionByZero`, `Overflow`.
- Les montants sont des `Decimal` ; les flottants et booléens monétaires sont refusés par les validateurs.
- Le résultat ne dépend pas du contexte Decimal de l’appelant (test dédié).
- Les scénarios travaillent sur une copie ; le dossier source n’est pas modifié.

### 5.2 Propagation des inconnues

Une donnée inconnue ne devient jamais zéro : elle propage `None` et un statut `incomplete`. Les tests couvrent les dettes sans échéancier, les revenus reportés inconnus, les frais essentiels hors total et les unités extrêmes. C’est un point fort majeur pour éviter les surestimations de capacité de remboursement.

### 5.3 Scoring

Le scoring explicable existe (critères, seuils, qualificatif, revue obligatoire), mais la fusion 70/30 est **inactive par conception** : `validated_grid: None`, `model: None`, `model_status: "disabled_by_design"`. Aucun score de probabilité de défaut n’est produit. C’est cohérent avec l’absence de grille validée et de modèle entraîné.

### 5.4 Limites métier

- Pas de conversion automatique d’une balance comptable en flux directs.
- Pas d’ingestion de transactions brutes ; les agrégats doivent exclure les transferts internes et les doubles mouvements.
- Les clés de périodes, flux directs, emplois financés et coûts nets nécessitent un rapprochement documentaire humain.
- Pas de projection automatique de croissance ni de simulation probabiliste.
- La recommandation et la décision restent au prêteur.

---

## 6. Sécurité

### 6.1 Authentification

**API Bearer**

- Identités exclusivement serveur (`CREDIT_AUTH_FILE` ou `CREDIT_AUTH_JSON`), jamais fournies par le corps HTTP.
- Jetons opaques hachés en SHA-256 dans le registre, comparaison en temps constant (`hmac.compare_digest`).
- Expiration, révocation, désactivation, rôle et institution validés à chaque requête.
- En production : registre fichier privé obligatoire, permissions `0o077` interdites, `CREDIT_AUTH_JSON` refusé, expiration et institution/rôle obligatoires.
- Limitation des échecs d’authentification par IP.

**Sessions web**

- Cookie opaque `HttpOnly`, `SameSite=Lax`, `Secure` en production, durée absolue 8 h, inactivité 30 min, maximum 5 sessions.
- Empreinte du secret de session en base (SHA-256), pas de jeton brut.
- Argon2id pour les mots de passe, vérification factice pour égaliser le coût, sémaphore de hachage.
- CSRF par nonce + contrôle exact de l’`Origin` sur toutes les mutations par cookie.
- Fixation de session évitée : le cookie présenté est supprimé à la connexion.
- Toute modification du registre invalide les sessions (empreinte du registre + révision + hash du mot de passe).

**Points faibles**

- Pas de MFA/SSO.
- Pas de fournisseur d’identité externe ; le registre local ne convient pas à des comptes bancaires privilégiés.
- Auto-inscription publique possible si `CREDIT_SIGNUP_INSTITUTION_ID` est défini, sans vérification de contact (voir AUD-06).
- `CREDIT_ENV` non validé (voir AUD-02).

### 6.2 Autorisation

- `authorize()` vérifie l’institution **et** le propriétaire, ou un `CaseGrant` explicite, ou `case_ids` du registre. Un administrateur n’a pas de contournement automatique.
- `enforce()` exige un rôle `STAFF` pour les routes d’analyse, documents, runs, process et événements internes.
- `client_fields()` bloque l’injection d’observations internes, d’identité contrôlée, d’apport vérifié, de preuves `verified` et de références de revue.
- `public_payload()` retire les champs internes avant sérialisation.
- Les rôles bancaires sont confinés aux routes `/bank/` et `/public/` par une dépendance dédiée.

**Points faibles**

- `enforce()` s’appuie sur des sous-chaînes de chemin (`"/assessments" in route`, `"/documents" in route`, etc.) : mécanisme fragile, à remplacer par des dépendances explicites par route.
- `public_payload()` est une liste de suppression, pas une projection allowlist : un nouveau champ interne ajouté demain pourrait fuiter.
- Pas de RLS PostgreSQL : le cloisonnement institutionnel est applicatif. Un identifiant DB compromis peut lire toutes les lignes autorisées par les `GRANT` table-level.

### 6.3 Isolation documentaire

- Worker éphémère en sous-processus, sans accès à la base.
- `harden()` : `umask 077`, `RLIMIT_CORE`, `PR_SET_NO_NEW_PRIVS`, abandon des privilèges root (`setuid`/`setgid` vers 65534), vérification des liens symboliques.
- Limites `RLIMIT_AS`, `RLIMIT_CPU`, `RLIMIT_FSIZE`, timeout, concurrence bornée, attente de créneau limitée.
- Environnement minimal transmis au worker.
- Décodage des images sur le contenu réel, pas sur l’extension/MIME.
- PDF actifs non exécutés ; le test synthétique vérifie qu’un JavaScript embarqué n’est pas exécuté.
- Antimalware ClamAV optionnel ; `not_scanned` n’est jamais présenté comme « sain ».
- Taille des corps bornée, profondeur/nombre de nœuds JSON bornés, timeout de réception.

**Points faibles**

- L’isolation reste une isolation de **processus** sur le même hôte, pas un bac à sable OS complet (pas de seccomp/AppArmor/namespace réseau dédié).
- Les clés de signature sont montées dans le même conteneur que l’API/worker partenaire (`compose.partners.yml`), ce qui augmente l’impact d’une compromission du worker.
- `printing/isolation.py` n’utilise pas `start_new_session` ni de kill de groupe de processus en cas de timeout ; le worker de rendu appelle toutefois `harden()` et n’ouvre pas de réseau.

### 6.4 Signatures et intégrité

- Ed25519 détaché sur un JSON canonique (`sort_keys`, séparateurs compacts, `allow_nan=False`).
- Trousseau serveur : `active`, `retired`, `revoked` ; usage `demonstration` ou `production` ; exactement une clé active applicable.
- Clé privée PEM PKCS#8, permissions `0o077` interdites, correspondance avec la clé publique vérifiée.
- Vérification de l’intégrité du manifeste, de l’enveloppe, des fichiers, du rattachement dossier/transmission/partenaire/attestation.
- Attestation expirée, révoquée ou remplacée détectée ; clé révoquée bloque les nouveaux envois.
- Page publique minimale : émetteur, identifiant, date, statut ; aucun fichier, aucune donnée financière.
- Ce n’est **pas** une signature PAdES ni une certification par un prestataire de confiance ; la documentation le dit explicitement.

### 6.5 Audit et journalisation

- Événement `SecurityEvent` en base pour chaque requête authentifiée : acteur, institution, méthode + nom de route, statut, `request_id`, `resource_id`.
- Journal JSON `credit.security` : date, événement, acteur, institution, résultat, `request_id`, `resource_id`.
- Aucun corps, URL brute, jeton ou donnée financière dans les journaux.
- Erreurs 500 génériques, `request_id` pour la corrélation, pas de traceback dans la réponse.
- `RequestValidationError` retire le champ `input` des erreurs.

**Points faibles**

- L’écriture `SecurityEvent` est synchrone dans le middleware ; si elle échoue, une réponse pourtant réussie est remplacée par un 503. Couplage disponibilité/audit.
- Table `security_events` non purgée, non partitionnée, sans collecteur externe.
- L’audit local n’est pas inviolable face à un administrateur DB/OS.

### 6.6 Durcissement de déploiement

- Docker : utilisateur non root (UID 10001), racine en lecture seule, `cap_drop: [ALL]`, `no-new-privileges`, `pids_limit`, `mem_limit`, `tmpfs` `nosuid,noexec`.
- `compose.production.example.yaml` : PostgreSQL TLS `verify-full`, registre privé monté, hôtes explicites, proxy de confiance explicite, démo interdite, antimalware requis.
- `entrypoint.py` : refuse un rôle PostgreSQL superuser/createdb/createrole/bypassrls, exige la tête Alembic en production, n’exécute pas les migrations avec le compte applicatif.
- `production_guard()` : PostgreSQL TLS, mot de passe explicite, hôtes non génériques, démo interdite, registre privé, permissions, proxy explicite.

**Points faibles**

- `CREDIT_ENV` non validé (AUD-02).
- L’antimalware n’est pas exigé par le garde lui-même (AUD-19).
- Pas de HSTS ni de `Permissions-Policy` explicite (le proxy peut les ajouter).
- Pas de TLS interne entre l’API et PostgreSQL si l’opérateur configure mal le DSN ; le garde l’impose en production, mais le Compose local ne l’applique pas.

---

## 7. Robustesse, performance et exploitation

### 7.1 Limites

| Limite | Valeur par défaut | Portée |
|---|---|---|
| Requêtes/IP | 600/min | Par processus |
| Requêtes/acteur | 600/min | Par processus |
| POST/acteur | 120/min | Par processus |
| Échecs auth/IP | 40/min | Par processus |
| JSON | 2 Mo, profondeur 40, 40 000 nœuds | Par requête |
| Dossiers/acteur | 1 000 | Applicatif |
| Documents/dossier | 500 | Applicatif |
| Paquet partenaire | 50 Mo | Applicatif |
| Sources sélectionnées | 20 | Applicatif |
| Revues/dossier | 20 | Applicatif |
| Compléments/transmission | 30 fichiers, 5 Mo, 30 pages | Applicatif |
| OCR/scan | timeout, mémoire, CPU, pixels, pages | Worker |
| Impression | timeout, pages, mémoire, entrée/sortie | Worker |

Les limites sont documentées comme **par processus**. Un déploiement multi-worker ou multi-instance multiplie les quotas ; il faut une passerelle ou un store partagé.

### 7.2 Concurrence

- Verrouillage optimiste et `If-Match`/révisions : bon.
- `get_record()` utilise `with_for_update()` pour les mutations.
- `dispatch()` verrouille dossier → transmission → outbox → partenaire, dans cet ordre, pour éviter les interblocages.
- Les tests PostgreSQL vérifient le claim unique de l’outbox et le refus de publication si le dossier change pendant l’envoi.
- **Point faible :** `dispatch()` effectue l’appel au connecteur **pendant** la transaction et en tenant les verrous. Une latence réseau longue bloque les lignes et la connexion, et peut saturer le pool.

### 7.3 Outbox et reprises

- Bail de 60 s, trois tentatives automatiques, temporisation exponentielle bornée, deux reprises manuelles.
- Clé stable de transmission, historique des tentatives.
- `partner_worker.py` traite jusqu’à 20 lignes par passe.
- **Point faible :** la boucle du worker n’isole pas chaque `dispatch()` par un `try/except` ; une exception inattendue (connecteur, bug, erreur DB non prévue) arrête la boucle. Le bail permet une reprise après redémarrage, mais sans supervision ni alerte.
- Pas de file de lettres mortes ni de métrique d’échec.

### 7.4 Base de données

- `sessions()` utilise `create_engine(url)` avec les réglages par défaut : pas de `pool_pre_ping`, pas de dimensionnement explicite, pas de `statement_timeout`.
- Les écritures d’audit et de `last_seen` ajoutent au moins deux écritures par requête authentifiée.
- Les colonnes `JSON` et `LargeBinary` peuvent produire des lignes volumineuses et des sauvegardes lourdes.
- SQLite est supporté pour les tests, mais la production exige PostgreSQL TLS.

### 7.5 Rétention, sauvegarde, restauration

- Aucune purge automatique.
- `docs/security/BACKUP_RESTORE.md` décrit une procédure manuelle, un test synthétique et les limites.
- Le script `verify_backup_restore.py` restaure une base et compare dossier, analyse, PDF, scan et audit.
- Le rôle runtime est testé sur `SELECT count(*) FROM cases` et quelques refus, mais **pas** sur les parcours web/partenaire/institution (voir AUD-01).
- Aucun RPO/RTO, chiffrement au repos ou restauration de production n’est annoncé comme vérifié.

### 7.6 Portabilité

Le code est fortement POSIX : `fcntl`, `resource.setrlimit`, `os.killpg`, `os.getuid`, `os.setuid`, `ctypes` `prctl`. Il ne s’exécute pas nativement sur Windows. Ce n’est pas un défaut si la cible est Linux, mais cela doit être explicite dans le README/CI et les scripts de développement.

---

## 8. Tests et preuves

### 8.1 Ce que les tests couvrent bien

- Calculs nominaux, inconnus, non applicables, montants invalides, ratios non calculables, arrondis, échéances irrégulières, dettes dupliquées, retenues salariales, coûts professionnels, prélèvements, financement/emploi, stress et retard.
- Propriétés mathématiques : principal remboursé, monotonie de la marge, indépendance du contexte Decimal, absence de renormalisation.
- API : migrations `upgrade head`/`downgrade base`, historique, redémarrage, `If-Match`, idempotence.
- Sécurité : fuite interne, analyse brute refusée, faux statut `verified`, auto-confirmation, jetons expirés/révoqués/désactivés, limitation, hôtes, corps chunked, erreurs sans payload, journal sans jeton.
- Documents : MIME trompeur, PDF natif refusé, OCR, pages, rotation/recadrage, revues périmées, worker timeout, concurrence, limites de taille, antimalware.
- Partenaires : parcours complet, rôles, double validation, invalidation, confirmation, retrait, expiration, révocation, rotation de clé, webhook HMAC/replay/ordre, concurrence PostgreSQL, worker outbox.
- Institutions : offres signées, refus, idempotence, isolation bancaire, comptes, activation, métriques, archivage, altération d’analyse, versions de compte, file de revue admin.
- Déploiement : port Render, tête Alembic `0010`, proxy Netlify, copie privée du registre.

### 8.2 Ce que les tests ne couvrent pas

- MFA/SSO, RLS, chiffrement au repos, HSM/KMS, fournisseur de signature tiers.
- Antivirus avec signatures réelles, sandbox OS complet, réseau isolé.
- Charge, résilience multi-instance, quotas distribués, supervision, alertes.
- Restauration d’un vrai environnement, rétention réelle, suppression légale.
- Validation métier/réglementaire des hypothèses et de la grille de score.
- Le script de droits runtime sur les parcours web/partenaire/institution (le test ne vérifie que `cases`).

### 8.3 Exécution dans cet environnement

La suite n’a pas été exécutée ici : Python 3.15.2 est installé, le projet exige `<3.14`, et les dépendances (`fastapi`, `sqlalchemy`, etc.) ne sont pas présentes. Les documents `VALIDATION.md` et `docs/security/RESULTATS.md` rapportent des exécutions antérieures (35, 181 puis 234 tests selon les rapports), mais ces chiffres ne sont pas reproductibles dans l’environnement courant. Il faut une CI Linux avec `uv sync --locked` et PostgreSQL dédié pour rejouer les preuves.

---

## 9. Constats détaillés

### 9.1 Tableau de synthèse

| ID | Sévérité | Constat | Preuve principale | Impact |
|---|---|---|---|---|
| AUD-01 | Élevé | Droits PostgreSQL runtime incomplets (0007–0010) | `ops/runtime_grants.sql` vs tables des migrations ; `web/application.py` fait `DELETE` sur `web_sessions` | Connexion web, sessions, partenaires et institutions en échec avec le rôle documenté |
| AUD-02 | Élevé | `CREDIT_ENV` non validé, gardes fail-open | `production_guard()` retourne si la valeur n’est pas exactement `production` ; `create_web_app`, `signing_key` | Une faute de frappe désactive HTTPS, cookie `Secure`, démo interdite, permissions du registre |
| AUD-03 | Élevé | Antimalware non exigé par le garde de production | `security/files.py` : `CREDIT_ANTIMALWARE_REQUIRED` défaut `false` ; seul Compose le force | Dépôts non scannés acceptés hors gabarit |
| AUD-04 | Élevé | Pas de MFA/SSO, pas de RLS, pas de chiffrement au repos, pas de rétention | `docs/security/AUDIT.md`, `BACKUP_RESTORE.md`, code | Risques incompatibles avec des données bancaires réelles |
| AUD-05 | Élevé | Isolation worker = processus, pas sandbox OS ; clés dans le même conteneur | `documents/isolation.py`, `security/worker.py`, `compose.partners.yml` | Compromission d’un parseur → accès aux fichiers/clés selon les montages |
| AUD-06 | Moyen | Audit DB synchrone à chaque requête, couplage disponibilité | `api.py` `trace` : insertion `SecurityEvent`, 503 si échec | Latence, écritures amplifiées, panne d’audit = panne métier |
| AUD-07 | Moyen | `public_payload` en liste de suppression | `security/access.py` | Fuite future si un champ interne est ajouté |
| AUD-08 | Moyen | `enforce()` par sous-chaînes de route | `security/access.py` | Autorisation fragile, contournement possible par nouvelle route |
| AUD-09 | Moyen | Auto-inscription sans vérification de contact | `web/registration.py` ; `contact_status=not_verified` | Comptes fictifs, spam, consommation de ressources |
| AUD-10 | Moyen | Binaires en base + absence de rétention | `persistence.py`, `partners/models.py`, `institutions/models.py` | Volume, sauvegardes, conformité |
| AUD-11 | Moyen | Limites par processus uniquement | `security/runtime.py` `Limiter`, sémaphores locaux | Multi-instance = quotas multipliés |
| AUD-12 | Moyen | Appel connecteur sous verrous/transaction | `partners/delivery.py` `dispatch` | Blocage de lignes, saturation du pool |
| AUD-13 | Moyen | Worker outbox sans isolation d’erreur par job | `scripts/partner_worker.py` | Arrêt de la boucle sur exception inattendue |
| AUD-14 | Moyen | Payload JSON non versionné | `persistence.py` `CaseRecord.payload` | Évolution de contrat non outillée |
| AUD-15 | Faible | `sessions()` sans `pool_pre_ping`/timeouts | `persistence.py` | Connexions mortes après redémarrage DB |
| AUD-16 | Faible | `create_app()` exécuté à l’import | `credit/api.py` fin de fichier | Effets de bord, tests/scripts dépendants de l’environnement |
| AUD-17 | Faible | Pas de HSTS/Permissions-Policy | `web/application.py` | Durcissement navigateur incomplet |
| AUD-18 | Faible | Nettoyage des sessions seulement à la connexion | `web/application.py` | Croissance de `web_sessions` |
| AUD-19 | Faible | Jeton de vérification en query string | `signing.verification_url` | Journalisation proxy possible |
| AUD-20 | Faible | POSIX-only | `resource`, `fcntl`, `os.killpg`, `os.setuid` | Pas de exécution native Windows |
| AUD-21 | Info | Documentation de validation hétérogène | `VALIDATION.md`, `RESULTATS.md`, `README.md` | Chiffres et dates différents, auditabilité |

### 9.2 Constats prioritaires

#### AUD-01 — Droits PostgreSQL runtime incomplets

**Constat.** `ops/runtime_grants.sql` accorde des droits sur les tables historiques (`cases`, `submissions`, `print_editions`, `analyses`, `assessments`, `documents`, `document_sources`, `document_runs`, `structured_inputs`, `document_reviews`, `document_events`, `print_events`, `print_publications`, `security_events`, `alembic_version`) mais **pas** sur les tables créées par 0007–0010 : `web_users`, `web_sessions`, `web_registrations`, `journey_drafts`, `case_grants`, `institution_workflow_policies`, `bank_partners`, `internal_reviews`, `partner_packet_files`, `internal_attestations`, `bank_transmissions`, `partner_outbox`, `partner_events`, `bank_attachments`, `institution_accounts`, `bank_decision_records`, `client_inbox_messages`. Il n’accorde pas non plus `DELETE` sur `web_sessions`, alors que `web/application.py` supprime la session précédente à la connexion, nettoie les sessions expirées et supprime la session à la déconnexion.

**Impact.** Si l’opérateur suit la procédure de `BACKUP_RESTORE.md`, le compte runtime ne peut pas :
- lire/écrire `web_users` et `web_sessions` → connexion web impossible ;
- créer un brouillon (`journey_drafts`) ;
- utiliser les parcours partenaires (revue, attestation, transmission, outbox) ;
- utiliser les consoles institution (comptes, décisions, boîte client).

Le test `verify_backup_restore.py` applique bien le script, mais ne vérifie que `SELECT count(*) FROM cases` et quelques refus ; il ne teste aucun parcours web/partenaire. Le constat est donc invisible dans la validation actuelle.

**Recommandation.**
1. Générer les `GRANT` à partir des métadonnées SQLAlchemy/Alembic, pas à la main.
2. Accorder au minimum :
   - `web_users` : `SELECT, INSERT, UPDATE` ;
   - `web_sessions` : `SELECT, INSERT, UPDATE, DELETE` ;
   - `web_registrations`, `journey_drafts`, `institution_workflow_policies`, `bank_partners`, `internal_reviews`, `internal_attestations`, `bank_transmissions`, `partner_outbox`, `institution_accounts` : `SELECT, INSERT, UPDATE` ;
   - `case_grants`, `partner_packet_files`, `partner_events`, `bank_attachments`, `bank_decision_records`, `client_inbox_messages` : `SELECT, INSERT` ;
   - conserver `SELECT, INSERT` sur les historiques append-only (`analyses`, `assessments`, `document_*`, `print_events`, `print_publications`, `security_events`).
3. Ajouter un test `SET ROLE` qui exécute : connexion web, création de brouillon, ouverture de revue, préparation/confirmation de transmission, réception bancaire, décision, activation de compte.
4. Vérifier aussi les séquences et les droits par défaut (`ALTER DEFAULT PRIVILEGES`) pour les futures tables.

#### AUD-02 — `CREDIT_ENV` non validé, gardes fail-open

**Constat.** `production_guard()` fait `if os.getenv("CREDIT_ENV", "local") != "production": return`. `create_web_app()` calcule `production = os.getenv("CREDIT_ENV", "local") == "production"`. `signing.signing_key()` teste `os.getenv("CREDIT_ENV") == "production"`. `credit/api.py` désactive Swagger seulement si la valeur est exactement `production`.

**Impact.** Une valeur `prod`, `Production`, `production ` (espace) ou une variable absente désactive silencieusement :
- l’exigence HTTPS et le cookie `Secure` ;
- l’interdiction de `CREDIT_ALLOW_DEMO` ;
- l’exigence de registre privé et de permissions `0o077` ;
- l’exigence PostgreSQL TLS `verify-full` ;
- l’exigence d’hôtes explicites et de proxy de confiance ;
- la désactivation de Swagger/OpenAPI ;
- le refus des clés de démonstration.

**Recommandation.**
1. Normaliser (`lower().strip()`) et valider la valeur dans un ensemble `{local, test, production}` au démarrage ; refuser toute autre valeur.
2. Faire échouer le démarrage si `CREDIT_ENV` est absent en production (ou si `CREDIT_PRODUCTION=true`).
3. Ajouter un test qui vérifie qu’une valeur inconnue refuse le démarrage.
4. Afficher le mode effectif dans `/health` (sans secret) et dans les journaux de démarrage.

#### AUD-03 — Antimalware non exigé par le garde de production

**Constat.** `security/files.py` lit `CREDIT_ANTIMALWARE_REQUIRED` avec un défaut `false`. Le gabarit `compose.production.example.yaml` le force à `true`, mais `production_guard()` ne le vérifie pas. Un déploiement Kubernetes, Render ou un Compose dérivé peut donc accepter des fichiers avec `status: not_scanned`.

**Impact.** Un PDF/image malveillant peut atteindre les parseurs (même isolés) sans détection. L’absence de scanner n’est pas présentée comme « sain », mais le dépôt est accepté.

**Recommandation.**
1. En production, exiger `CREDIT_ANTIMALWARE_REQUIRED=true` et un `clamscan` disponible au démarrage (ou un service de scan configuré).
2. À défaut, refuser le démarrage ou bloquer tous les dépôts avec un message explicite.
3. Tester le cas « scanner absent + production » et « scanner présent + EICAR ».

#### AUD-04 — Limites de sécurité d’infrastructure

**Constat.** Les documents `docs/security/AUDIT.md` et `findings.json` reconnaissent déjà :
- pas de MFA/SSO ;
- pas de RLS PostgreSQL (cloisonnement applicatif seulement) ;
- pas de chiffrement au repos applicatif ;
- pas de rétention/purge ;
- audit local non inviolable ;
- pas de fournisseur de signature tiers/HSM ;
- pas de supervision/alerting de production.

**Impact.** Ces limites empêchent une homologation bancaire réelle, même si le code applicatif est solide. Un identifiant DB compromis peut lire toutes les lignes autorisées par les `GRANT` table-level ; un administrateur DB peut altérer l’audit ; une sauvegarde non chiffrée expose les PDF et données personnelles.

**Recommandation.** Traiter ces points comme des prérequis de production, pas comme des améliorations :
- OIDC/SAML + MFA pour les rôles analyste/manager/admin/banque ;
- RLS PostgreSQL par `institution_id` et rôle DB par usage ;
- chiffrement des volumes/sauvegardes + KMS, chiffrement colonne pour les données les plus sensibles ;
- collecteur d’audit externe, horodatage, rétention et supervision ;
- HSM/KMS ou service de signature séparé pour les clés de production ;
- politique de rétention validée juridiquement.

#### AUD-05 — Isolation worker et clés de signature

**Constat.** `credit/documents/isolation.py` et `credit/printing/isolation.py` lancent des sous-processus durcis (`harden`, `no_new_privs`, `setuid` si root, rlimits, timeout, environnement minimal). Mais :
- le système de fichiers de l’hôte reste visible selon les montages ;
- il n’y a pas de namespace réseau/seccomp/AppArmor dédié ;
- `compose.partners.yml` monte le répertoire de signature dans le conteneur `api` et dans le worker outbox, donc une compromission du worker partenaire peut atteindre les clés privées.

**Impact.** Un parseur PDF/image compromis peut, selon le déploiement, lire des fichiers accessibles à l’UID du worker ou les clés montées. L’isolation réduit la surface mais ne constitue pas un bac à sable complet.

**Recommandation.**
1. Exécuter les parseurs dans un conteneur/sandbox dédié : rootfs read-only, pas de réseau, seccomp/AppArmor, utilisateur non privilégié, tmpfs éphémère.
2. Séparer le service de signature (ou HSM/KMS) du service qui décode les fichiers.
3. Ne jamais monter les clés privées dans le conteneur qui traite des fichiers non fiables.
4. Tester avec des fichiers hostiles réels (PDF malformés, images polyglottes, bombes de décompression).

#### AUD-06 — Audit synchrone et couplage disponibilité

**Constat.** Dans `credit/api.py`, le middleware `trace` insère un `SecurityEvent` pour chaque requête authentifiée. Si l’insertion échoue, il remplace la réponse par un 503 « Historique de sécurité indisponible ». `web_sessions.last_seen` est également mis à jour et commité à chaque requête web.

**Impact.**
- Une panne ou un verrou sur `security_events` transforme des lectures réussies en erreurs.
- Deux écritures minimum par requête authentifiée : latence et charge.
- `security_events` croît sans purge ni partitionnement.
- Un attaquant authentifié peut amplifier les écritures.

**Recommandation.**
1. Découpler l’audit du chemin de réponse : file interne/outbox, écriture asynchrone, collecteur externe.
2. Si le choix est de rester fail-closed, le documenter comme décision explicite et prévoir une alerte.
3. Partitionner/archiver `security_events`, définir une rétention.
4. Éviter le commit `last_seen` à chaque requête : mise à jour throttlée (par exemple une fois par minute) ou en mémoire avec flush périodique.

#### AUD-07 — `public_payload` en liste de suppression

**Constat.** `security/access.py` retire explicitement `record_details.internal_observations` et `analysis_details.identity`. Tout autre champ interne ajouté au payload sera exposé par défaut à un demandeur.

**Impact.** Régression de confidentialité lors d’une évolution de contrat. Le test actuel ne vérifie que les deux champs connus.

**Recommandation.**
1. Définir une projection **allowlist** par audience (`applicant`, `analyst`, `bank`, `public`) et sérialiser uniquement les champs autorisés.
2. Ajouter un test de contrat qui échoue si un nouveau champ apparaît dans la projection demandeur sans classification explicite.
3. Centraliser la classification des champs (public/interne/secret) dans un schéma unique.

#### AUD-08 — `enforce()` par sous-chaînes de route

**Constat.** `enforce()` décide qu’une route est interne si son chemin contient `"/assessments"`, `"/analyses"`, `"/scenarios"`, `"/documents"`, `"/runs/"`, ou se termine par `/events` ou `/process`. C’est une heuristique.

**Impact.** Une nouvelle route interne dont le chemin ne contient pas ces motifs peut être accessible à un demandeur. À l’inverse, une route publique dont le chemin contient `"/documents"` peut être bloquée à tort. Le comportement dépend des noms de routes, pas d’une politique explicite.

**Recommandation.**
1. Remplacer l’heuristique par une dépendance `require_staff` explicite sur chaque route interne, ou par un décorateur de permission.
2. Ajouter un test paramétré qui énumère toutes les routes et vérifie la permission attendue.
3. Documenter la matrice route → rôle dans un fichier unique.

#### AUD-09 — Auto-inscription sans vérification de contact

**Constat.** `POST /auth/register` crée un `WebUser` activé (`enabled=1` par défaut) et un `WebRegistration` avec `contact_status="not_verified"`. La connexion par mot de passe fonctionne immédiatement. Le seul garde-fou est `CREDIT_SIGNUP_INSTITUTION_ID` (désactivé si vide) et une limite de 5 demandes/heure/IP/identifiant.

**Impact.** Création de comptes fictifs, spam, consommation de ressources (jusqu’à 1 000 dossiers par acteur), utilisation des fonctionnalités demandeur sans preuve de possession de l’e-mail/téléphone. Pas de CAPTCHA ni de vérification.

**Recommandation.**
1. Désactiver l’auto-inscription par défaut en production ; privilégier l’invitation nominative ou un parcours vérifié.
2. Ajouter vérification e-mail/SMS (code à usage unique) avant activation complète, ou limiter les fonctionnalités tant que `contact_status != verified`.
3. Ajouter CAPTCHA/WAF, quotas globaux et alerting sur les créations.
4. Tester le parcours « compte non vérifié » et les limites distribuées.

#### AUD-10 — Binaires en base et absence de rétention

**Constat.** Les originaux, dérivés, paquets, pièces jointes et PDF de décision sont en `LargeBinary` dans PostgreSQL. Aucune purge automatique n’est active. Les sauvegardes incluent donc tous les fichiers.

**Impact.** Croissance non bornée, sauvegardes lourdes, restauration lente, coût, difficulté à respecter une durée de conservation ou une demande d’effacement.

**Recommandation.**
1. Évaluer un stockage objet chiffré (S3 compatible) avec URLs signées courtes, ou au minimum partitionner/archiver les tables binaires.
2. Définir une politique de rétention par type (dossier, pièce, audit, PDF, sauvegarde) et l’outiller.
3. Mettre en place des quotas par institution et une facturation/alerte de stockage.
4. Tester la restauration et la purge sur des copies synthétiques.

#### AUD-11 — Limites par processus

**Constat.** `Limiter` est une structure en mémoire (`OrderedDict` + `deque`) protégée par un verrou local. Les sémaphores OCR/impression sont également locaux. La documentation le reconnaît.

**Impact.** En multi-worker Uvicorn ou multi-instance, les quotas sont multipliés ; un attaquant peut contourner la limitation d’authentification ou de POST en répartissant les requêtes.

**Recommandation.**
1. Utiliser un store partagé (Redis) ou une passerelle/API gateway pour les limites.
2. Ajouter des quotas par institution/acteur au niveau base ou gateway.
3. Si le déploiement reste mono-instance, le documenter comme contrainte explicite et vérifier la configuration Uvicorn.

#### AUD-12 — Appel connecteur sous verrous

**Constat.** `dispatch()` verrouille le dossier, la transmission, l’outbox et le partenaire, puis appelle le connecteur externe avant de commit. Le bail est de 60 s.

**Impact.** Une latence réseau élevée bloque les lignes et la connexion ; plusieurs dispatches concurrents peuvent saturer le pool ; les autres opérations sur le dossier attendent.

**Recommandation.**
1. Claim transactionnel court : marquer `processing`, commit, puis appeler le connecteur hors transaction.
2. Recharger et vérifier l’état après l’appel, avec la clé d’idempotence stable.
3. Configurer des timeouts courts et un pool dimensionné ; ajouter des métriques de durée.

#### AUD-13 — Worker outbox sans isolation d’erreur

**Constat.** `scripts/partner_worker.py` boucle sur les IDs et appelle `dispatch(session, id)` sans `try/except`. `dispatch()` capture `(TimeoutError, ValueError, HTTPException, KeyError)` mais pas les autres exceptions (bug de connecteur, `TypeError`, erreur DB inattendue).

**Impact.** Une exception inattendue arrête la boucle ; le job reste `processing` jusqu’à expiration du bail (60 s) et nécessite un redémarrage ou une nouvelle passe.

**Recommandation.**
1. Encadrer chaque `dispatch()` par `try/except Exception` avec journalisation et poursuite de la boucle.
2. Ajouter une file de lettres mortes après N échecs et une alerte.
3. Tester un connecteur qui lève une exception inattendue.

#### AUD-14 — Payload JSON non versionné

**Constat.** `CaseRecord.payload` est un JSON libre validé à l’entrée, sans `schema_version`. Les contrats Pydantic évoluent avec le code.

**Impact.** Un ancien dossier peut ne plus être validable après une évolution de contrat ; les migrations de données ne sont pas outillées ; les tests de compatibilité historique sont limités.

**Recommandation.**
1. Ajouter un `schema_version` dans le payload et des validateurs backward-compatible.
2. Écrire des migrations de données pour les changements incompatibles.
3. Tester la lecture d’un dossier créé avec une version antérieure.

### 9.3 Constats secondaires

- **AUD-15 — Pool DB par défaut.** `create_engine(url)` sans `pool_pre_ping`, `pool_size`, `max_overflow` ni `statement_timeout`. Recommandation : paramétrer et surveiller.
- **AUD-16 — `create_app()` à l’import.** `credit/api.py` termine par `app = create_app()`. Les scripts qui importent le module déclenchent `production_guard()` et la création du moteur. Recommandation : fabrique explicite, `uvicorn --factory`.
- **AUD-17 — En-têtes navigateur.** CSP, `nosniff`, `Referrer-Policy`, `Cache-Control` sont présents ; HSTS et `Permissions-Policy` manquent. Recommandation : les ajouter au proxy ou à l’application en production.
- **AUD-18 — Nettoyage des sessions.** Les sessions expirées sont supprimées à la connexion, pas par un job périodique. Recommandation : tâche de nettoyage planifiée.
- **AUD-19 — Jeton de vérification en query string.** `verification_url` place le jeton dans `?id=`. Le `Referrer-Policy: no-referrer` réduit la fuite, mais les journaux proxy peuvent conserver l’URL. Recommandation : ne pas journaliser les query strings, ou utiliser un fragment/POST.
- **AUD-20 — POSIX-only.** `resource`, `fcntl`, `os.killpg`, `os.setuid`, `ctypes` `prctl`. Recommandation : documenter Linux uniquement, CI Linux, imports conditionnels pour les tests de calcul purs.
- **AUD-21 — Documentation de validation hétérogène.** `VALIDATION.md` (4 nov.) parle de 35 tests, `RESULTATS.md` de 234, `README.md` de 181. Recommandation : un seul rapport daté par commit, avec commande et environnement.

---

## 10. Plan d’action priorisé

### P0 — Avant toute exposition à des données réelles

1. **Corriger `ops/runtime_grants.sql`** et ajouter un test `SET ROLE` couvrant web, partenaires et institutions (AUD-01).
2. **Valider `CREDIT_ENV`** et faire échouer le démarrage sur valeur inconnue (AUD-02).
3. **Exiger l’antimalware en production** ou bloquer les dépôts (AUD-03).
4. **Mettre en place MFA/SSO, RLS, chiffrement au repos, audit externe et rétention** (AUD-04).
5. **Séparer le service de signature** des parseurs et renforcer la sandbox (AUD-05).
6. **Découpler l’audit** du chemin de réponse et borner la table (AUD-06).

### P1 — Avant un pilote contrôlé

7. Remplacer `public_payload` par une projection allowlist (AUD-07).
8. Remplacer `enforce()` par des permissions explicites par route (AUD-08).
9. Encadrer l’auto-inscription (vérification, CAPTCHA, quotas) (AUD-09).
10. Définir une stratégie de stockage/rétention des binaires (AUD-10).
11. Externaliser les limites de débit (AUD-11).
12. Sortir l’appel connecteur de la transaction (AUD-12).
13. Isoler les erreurs du worker outbox et ajouter une file de lettres mortes (AUD-13).
14. Versionner les payloads JSON et outiller les migrations de données (AUD-14).

### P2 — Qualité et exploitation continue

15. Paramétrer le pool DB, `pool_pre_ping`, timeouts (AUD-15).
16. Passer à une fabrique d’application explicite (AUD-16).
17. Ajouter HSTS/Permissions-Policy (AUD-17).
18. Planifier le nettoyage des sessions (AUD-18).
19. Réduire la journalisation des jetons/URL (AUD-19).
20. Documenter Linux-only et ajouter une CI Linux (AUD-20).
21. Unifier les rapports de validation (AUD-21).

---

## 11. Conclusion

Le backend Crédit PME est **bien au-dessus d’un prototype jetable** : les contrats sont stricts, les calculs sont déterministes, les inconnues ne deviennent pas zéro, l’historique est immuable, les accès sont contrôlés par objet et par institution, et les parcours partenaires sont sérieusement modélisés (revue, attestation, consentement, outbox, décisions, offres).

Mais l’audit confirme la conclusion déjà présente dans `docs/security/AUDIT.md` : **la plateforme n’est pas prête pour la production**. Les risques les plus concrets ne sont pas dans les formules financières, mais dans l’exploitation : droits SQL incomplets, configuration d’environnement fail-open, antimalware non obligatoire, absence de MFA/RLS/chiffrement/rétention, isolation de processus insuffisante, audit couplé et limites locales.

La prochaine étape recommandée est double :

1. **Corriger les points P0** ci-dessus et rejouer les tests sur une CI Linux avec PostgreSQL dédié, y compris un test `SET ROLE` des parcours web/partenaire/institution.
2. **Faire valider par les métiers et les instances compétentes** les hypothèses financières, la grille de score (aujourd’hui volontairement inactive) et le cadre de partage bancaire, avant toute exposition à des dossiers réels.

Tant que ces deux étapes ne sont pas franchies, l’usage doit rester **local, synthétique et supervisé**.
