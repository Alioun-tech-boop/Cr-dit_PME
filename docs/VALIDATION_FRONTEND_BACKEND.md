# Validation exécutée — 5 novembre 2026

## Référence et périmètre

Dépôt backend existant, migration initiale 0006, interface fournie dans
`credit-pme-frontend-source.zip`. Avant modification : **234 tests backend réussis**,
**62 contrôles frontend réussis**. Aucun document client utilisé.
Les quatre feuilles CSS d’origine ont été comparées octet par octet : identiques.
Les changements portent sur les contrats HTTP, l’authentification, les commandes
et la restitution ; les menus, images, animations, onglets et aides sont conservés.

## Vérifications finales réellement exécutées

| Commande / contrôle | Résultat |
|---|---|
| `.venv/bin/python -m pytest -q --tb=short` | **242 réussis**, 2 avertissements, 135,87 s |
| `TEST_DATABASE_URL=postgresql+psycopg://credit:credit_local@127.0.0.1:5432/credit_test .venv/bin/python -m pytest -q --tb=short` | **242 réussis**, 2 avertissements, 144,17 s |
| `(cd frontend && npm test)` | **30 contrats + 39 contrôles + 3 frontières asynchrones** ; construction et syntaxe des 9 scripts réussies |
| `.venv/bin/python frontend/tests/verify_backend.py /workspace` | **20 contrôles réussis**, contrats Pydantic, invariants et noyaux réels |
| `(cd modules/credit_pme_pdf && ../../.venv/bin/python -m unittest discover -s tests -v)` | **167 tests réussis**, 10,093 s |
| `.venv/bin/python -m scripts.run_frontend_e2e` | **50 contrôles Chromium réussis**, zéro erreur JavaScript |
| `.venv/bin/ruff check credit scripts tests migrations` | Réussi |
| `git diff --check` | Réussi |
| `(cd frontend && npm audit --json)` | Aucune vulnérabilité signalée dans la résolution consultée |
| `.venv/bin/python -m scripts.check_secrets` | 237 fichiers texte examinés, aucune correspondance des détecteurs ciblés |
| `.venv/bin/python -m alembic current` | **0007 (head)** sur la base locale |
| `docker compose config --quiet` | Configuration locale valide |
| Construction Docker avec bundle CA du proxy | Réussie ; lancement du conteneur **non validé**, voir incident ci-dessous |
| `curl --fail http://127.0.0.1:8000/health` et lecture `/` | Uvicorn natif + PostgreSQL : `{"status":"ok"}` et HTTP 200 |

Les deux avertissements pytest concernent la dépréciation du transport httpx de
Starlette TestClient et de l’alias AnyIO BlockingPortal. Aucun test n’a été supprimé
ou son assertion financière affaiblie pour masquer une erreur.
Les avis npm et le détecteur ciblé de secrets ne constituent pas un audit exhaustif.

## Parcours Chromium vérifiés

Un serveur Uvicorn réel, une base SQL persistante et des comptes synthétiques isolés
sont créés par le script, puis le serveur est arrêté. Chromium système est utilisé
via `playwright-core` verrouillé ; aucune réponse financière n’est simulée.

- Connexion par formulaire, cookie HttpOnly, session et nonce CSRF.
- Particulier et entreprise : création du brouillon incomplet dans le formulaire,
  rechargement, reprise et validation de la saisie.
- Dépôt réel de PDF, PNG et JPEG ; PDF multipage logique issu de plusieurs sources,
  ordre, rotation et recadrage enregistrés puis vérifiés dans la réponse serveur.
- Réponse d’upload volontairement perdue **après réception réelle par le serveur** :
  reprise après rechargement, un seul original conservé pour cet envoi.
- Confirmation technique, OCR français réel des scans, extraction native du relevé,
  consultation des preuves, justification et enregistrement de revue humaine.
- Habilitation de l’analyste ajoutée exclusivement au registre serveur ; les
  sessions antérieures sont invalidées par cette modification.
- Affichage des 7 sections particuliers et des 9 sections entreprises.
- Marges nominales vérifiées : **70 000 FCFA** et **350 000 FCFA**.
  Après baisse de 20 % : **−30 000 FCFA** et **−450 000 FCFA** dans ces fixtures.
- Suggestions réelles, simulation, retour au scénario de base et communication
  explicite. Les observations, règles, sources et scores internes sont absents du
  modèle JSON demandeur, pas simplement masqués par l’interface.
- Téléchargements PDF autorisés dans le navigateur pour les deux noyaux.
- Écriture concurrente préparée sur le serveur, refus If-Match 409, puis résolution
  par rechargement explicite des champs du dossier métier.
- Accès inter-institutions refusé, expiration réelle d’une session en base,
  retrait des données privées de l’interface et déconnexion avec révocation.
- En viewport mobile 390 × 844 : onglet actif centré, menu et aide contextuelle.

Des tests JavaScript supplémentaires vérifient qu’une réponse tardive d’analyse
ou de simulation ne réaffecte pas un autre dossier ou une session remplacée.

Les tests backend supplémentaires couvrent aussi l’isolation entre deux utilisateurs
*d’une même institution*, les images originales et dérivées, tâches et éditions,
les clés d’idempotence incompatibles, le CSRF, les champs de profil invalides,
la compatibilité Bearer et le provisionnement CLI réel (hash, rôle inchangé,
révocation et événement d’administration atomique).

## Rendu et sources

Captures desktop et mobile générées et inspectées. Deux PDF demandeur ont été
réellement téléchargés puis leur texte extrait : 2 pages chacun, 2 253 et 2 311
caractères dans la première vérification, accents et devise présents, score interne
absent. Les **quatre pages PDF** ont été rendues en images et inspectées : pas de
troncature constatée sur ces fixtures, pieds de page et mentions d’analyse incomplète
lisibles. Les marges nominales imprimées correspondent aux résultats du moteur.
Cette inspection ne valide pas toutes les mises en page possibles ni des dossiers réels.

Traces exclues de Git dans `output/frontend/` :

- `backend-baseline.log`, `frontend-baseline.log` : références initiales.
- `backend-complete.log`, `backend-postgres-complete.log` : suites finales.
- `pdf-module-tests.log`, `npm-audit.json`, `secrets-check.json`.
- `browser-final.log` et `browser-6d0guh6a/` : dernière exécution des 50 contrôles.
- `browser-d69ojbx6/` : PDF, texte extrait et images des quatre pages inspectées.
- `docker-build.log`, `compose-start.log` : construction et échec de lancement.

## Incident de capacité et limites restantes

Le disque de l’environnement fait 7,9 Go et Docker utilise vfs. La construction de
l’image a réussi, mais sa copie pour créer le conteneur a échoué par manque d’espace.
Cette saturation a provoqué deux exécutions de tests interrompues (167 réussis /
74 erreurs et 178 réussis / 63 erreurs). Leurs traces sont conservées ; ces
exécutions ne sont pas comptées comme réussies.
Les caches de téléchargement et de construction créés pendant le travail ont été
nettoyés, sans suppression du volume PostgreSQL. Après libération d’espace, les
suites complètes ont été **réexécutées et ont toutes réussi** comme indiqué ci-dessus.
L’image de construction a été retirée pour libérer l’espace ; elle doit être
reconstruite sur un hôte suffisamment dimensionné. Le service local actuel utilise
Uvicorn natif, pas un conteneur API annoncé à tort comme opérationnel.

L’hébergement statique mentionné dans `frontend/.openai/hosting.json` n’est pas
reconfiguré ni déployé. Une origine HTTPS, une passerelle de même origine et les
identités métier approuvées restent nécessaires pour un déploiement extérieur.
Le mot de passe d’un utilisateur réel doit être provisionné par l’opérateur ; aucun
compte réel ni mot de passe par défaut n’a été créé pour présenter une connexion fictive.

Autres limites explicites : revue et rattachement avancés par éditeur JSON,
100 dossiers par noyau / 100 brouillons récents dans cette interface, absence de SSO,
MFA et récupération publique de mot de passe, limites de requêtes par processus,
antimalware non disponible localement. Les scans ne sont jamais déclarés authentiques.
Aucun modèle prédictif validé ni politique bancaire approuvée n’a été inventé.
Cette validation ne constitue pas une certification de sécurité ou de justesse bancaire.
