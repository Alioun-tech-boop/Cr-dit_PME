# Transmission bancaire — parcours versionné v1

Consulter les [vérifications réellement exécutées](VALIDATION_TRANSMISSION_BANCAIRE.md).

Le module `credit/partners/` ajoute un parcours réel de revue, signature, consentement,
transmission et réception. **Aucune banque réelle n’est préconfigurée.** Le portail
fonctionne avec les comptes partenaires provisionnés côté serveur ; le connecteur
`api_demo` n’effectue aucun appel réseau et ne représente pas une API bancaire réelle.

## Démonstration locale reproductible

Linux, Python 3.12, Node 20 ou ultérieur. Depuis la racine :

```bash
uv sync --locked
cd frontend && npm ci && npm run build && cd ..
.venv/bin/python -m scripts.prepare_partner_demo --directory .local/partner-demo/session-1 --origin http://127.0.0.1:8006
source .local/partner-demo/session-1/env.sh
.venv/bin/uvicorn credit.web.application:app --host 127.0.0.1 --port 8006 --no-access-log
```

Le préparateur refuse d’écraser une base ou un registre existant. Il crée explicitement
une base SQLite isolée, applique les migrations, crée une clé de **démonstration**, une
institution fictive et une banque fictive. Les identifiants sont `demo-applicant`,
`demo-analyst`, `demo-manager`, `demo-admin`, `demo-bank`. Les mots de passe aléatoires
sont dans `.local/partner-demo/session-1/accounts.private.json` (permissions 600).
Ne jamais versionner, publier ou transmettre ce fichier. Aucun mot de passe ni jeton
technique n’est embarqué dans le frontend. Les comptes de démonstration expirent après
24 heures ; les données restent conservées. Employer un nouveau répertoire pour une
nouvelle démonstration, sans supprimer les éditions de la précédente.

Dans un second terminal, pour la transmission autonome :

```bash
source .local/partner-demo/session-1/env.sh
.venv/bin/python -m scripts.partner_worker
# Une seule passe, si souhaité :
.venv/bin/python -m scripts.partner_worker --once
```

Ouvrir exactement `http://127.0.0.1:8006` ; utiliser des profils de navigateur distincts :

1. **Analyste** : ouvrir un dossier synthétique depuis « Mes demandes », lancer
   l’analyse existante, puis « Revue interne et attestation ». Sélectionner l’analyse
   et les sources nécessaires ; ouvrir la revue fige les PDF et le manifeste.
2. **Responsable** : ouvrir la revue, examiner les fichiers, saisir le motif interne
   et les réserves **communicables**, puis approuver. Émettre l’attestation signée.
3. **Demandeur** : « Choisir ma banque », actualiser la validation si nécessaire,
   consulter la banque fictive, sélectionner les pièces et prévisualiser. Déclarer
   sa qualité/pouvoir d’agir et cocher la confirmation, qui n’est jamais précochée.
4. Le worker traite la file ; le bouton « Lancer la transmission en attente » peut
   aussi déclencher une tentative autorisée. Un clic de choix bancaire seul n’envoie rien.
5. **Banque** : accéder à « Espace bancaire », consulter le paquet reçu, vérifier son
   intégrité et accuser réception. Demander des compléments, communiquer un avis ou
   une offre selon les habilitations. Une offre formelle exige un responsable bancaire,
   une référence externe et une pièce jointe explicitement communiquée.
6. **Demandeur** : actualiser le suivi, déposer les compléments demandés et confirmer
   leur partage séparément. Un dépôt seul ne les rend pas accessibles à la banque.

Les événements et notifications sont **internes à l’application**, consultables et
actualisables ; aucun email, SMS ou document financier en pièce jointe n’est envoyé.
Le demandeur dispose d’un accès permanent au choix/suivi depuis les dossiers et le
tableau de bord. Une validation actuelle détectée à la reprise du tableau de bord
oriente vers le choix bancaire. Les contrôles restent côté serveur même en saisissant
une URL directement.

## Installation sur le projet existant

La migration additive `0008` crée les partenaires, politiques de revue, droits de
revue explicites, revues internes, fichiers privés, attestations, transmissions,
outbox, événements et pièces de réponse. Elle ne modifie ni les analyses historiques
ni les PDF déjà émis.

```bash
# Avec DATABASE_URL et CREDIT_AUTH_FILE configurés pour votre environnement :
.venv/bin/alembic upgrade head
.venv/bin/uvicorn credit.web.application:app --host 127.0.0.1 --port 8000 --no-access-log
.venv/bin/python -m scripts.partner_worker
```

Les nouveaux rôles `bank_agent` et `bank_manager` sont provisionnés exclusivement par
l’opérateur, avec une institution vérifiée. Les outils existants `init_local_auth.py`
et `provision_web_user.py` restent utilisables ; aucune route de libre inscription
ou d’auto-attribution de rôle/institution n’est ajoutée.

Pour Docker, l’extension optionnelle `compose.partners.yml` ajoute un montage de clés
**en lecture seule** et le worker. Elle exige `CREDIT_PARTNER_SIGNING_DIRECTORY`, un
répertoire existant dont le trousseau utilise des chemins `/run/credit-signing/...`.
Les fichiers privés doivent être lisibles par l’UID 10001 du service et rester en
mode 600 ; ne pas les rendre publics pour contourner une erreur de permission.
L’API et le worker doivent partager le registre d’identités serveur existant.

```bash
docker compose -f compose.yaml -f compose.partners.yml config --quiet
# Après configuration explicite des clés, comptes et de la base :
docker compose -f compose.yaml -f compose.partners.yml up --build -d
```

Le contrôle d’accès de l’hébergement reste distinct des sessions métier. Si le site
est derrière une porte d’accès globale, décider explicitement si les deux seules
ressources de vérification publique peuvent être accessibles : `verify-attestation.html`
et `/api/public/attestations/{token}`. Ne pas ouvrir les routes de rapports privés.

## États, versions et indépendance des décisions

| Objet | États / signification |
|---|---|
| Analyse | Absente ou terminée selon les analyses réellement persistées ; aucun accord induit |
| Revue | `internal_review`, `second_validation`, `needs_completion`, `approved`, `not_approved`, `superseded` |
| Attestation | `valid`, `expired`, `revoked`, `replaced` ; l’intégrité et le statut de clé sont vérifiés séparément |
| Transmission | `ready`, `pending`, `sending`, `transmitted`, `received`, `under_review`, `additional_information`, `decision_available`, `failed`, `cancelled`, `withdrawn` |
| Décision bancaire | `favorable_opinion`, `conditional_offer`, `formal_offer`, `refused`, `disbursement_confirmed` ; auteur, motif, date et référence conservés |

Une revue porte sur le numéro de version du dossier, l’instantané de l’analyse, ses
validations documentaires actuelles, une empreinte du périmètre documentaire et la
version de la politique institutionnelle. L’empreinte couvre conservativement toutes
les pièces du dossier, pas seulement les pièces finalement partagées.

Les modifications de champs, pièces, géométrie, extractions, données structurées ou
revues documentaires remplacent l’autorisation de revue en cours ou approuvée. Une
nouvelle analyse et une nouvelle approbation sont demandées. Les données historiques,
PDF et paquets copiés restent immuables. Une nouvelle approbation remplace aussi les
anciennes attestations. Une modification de politique rend les validations antérieures
inutilisables pour les envois futurs. Les institutions reçoivent toujours la version
identifiée dans leur manifeste, même si le dossier courant évolue ensuite.

Le demandeur ne peut pas s’auto-approuver. La politique configure de un à trois
signataires distincts et, par défaut, exige que l’auteur de l’analyse soit différent
des approbateurs. Les réserves deviennent obligatoires lorsque la politique autorise
explicitement une approbation malgré des données incomplètes ou des déficits.
Aucun score ni résultat financier n’est réécrit pour rendre la revue favorable.

Le dossier doit appartenir à un compte demandeur. Pour une saisie initiale par un
responsable, l’affectation initiale à un demandeur de la même institution est tracée ;
la réaffectation d’un dossier client existant ou déjà en revue est refusée.
La demande de revue donne accès uniquement à l’équipe nommée dans la politique,
avec des appartenances institutionnelles contrôlées côté serveur.

## Partenaires et activation

Un partenaire conserve dénomination et présentation autorisées, pays, périmètre,
profils, produits, catégories nécessaires/autorisées, conditions effectivement fournies
et date, mode de réception, connexion, vérifications et activation. Aucun logo,
taux, frais ou délai non fourni n’est inventé ; aucun classement de banques n’est ajouté.

Étapes administratives :

1. Configurer la politique de l’institution avec ses signataires, portée, références
   de décision interne et revue juridique.
2. Créer le partenaire en `preparation`, avec son identifiant institutionnel distinct.
3. Provisionner et vérifier ses représentants ; créer leurs comptes bancaires.
4. Tester la réception locale ; le test exige un compte bancaire actif. Il ne valide
   pas une API bancaire externe lorsqu’il s’agit du portail ou du simulateur.
5. Consigner les références d’accord, de représentation, de partage et de revue juridique.
6. Activer : `active` pour le réel ou `demonstration` pour le synthétique. Suspension,
   indisponibilité et retour en préparation interrompent les envois futurs.

Seul un administrateur de l’institution émettrice peut modifier ce référentiel. La
création ne permet pas de passer un statut `active` dans le corps. Les versions sont
contrôlées et une configuration changée exige une nouvelle prévisualisation et
confirmation. Les banques de démonstration sont refusées pour un dossier réel et en
production. Les catégories documentaires sont vérifiées contre le catalogue existant.

## Paquet et consentement

Le paquet soumis à approbation contient les PDF déclaratifs adaptés au noyau, la
demande, l’identification, le budget/flux, les dettes, une synthèse, un rapport destiné
au prêteur et l’inventaire. Les sources originales ne sont ajoutées que par sélection
explicite ; elles doivent appartenir au même dossier, être confirmées et communicables.
Les documents internes non communicables sont refusés.

Le rapport prêteur utilise un modèle de présentation dédié qui exclut notes internes,
instantanés complets et commentaires de validation confidentiels **avant le rendu**.
Il reprend les indicateurs, limites et suggestions disponibles, sans inventer de score.
Les justificatifs restent des fichiers distincts : aucun PDF signé n’est fusionné ou
rasterisé pour l’export. Toutes les éditions sont privées en base (même stockage que
les PDF existants), avec identifiants, tailles, sources et empreintes SHA-256.

Pour une banque choisie, le serveur n’accepte que les catégories autorisées et exige
les catégories requises. La prévisualisation affiche le destinataire, les conditions,
les fichiers, leurs empreintes, la finalité/notice, l’attestation et la version du texte.
Le consentement conserve utilisateur, pouvoir déclaré, référence du pouvoir lorsqu’elle
est exigée, banque, version, manifeste, texte et date. Les réserves ne certifient pas
l’authenticité des justificatifs. Les exigences de mandat relèvent de la politique
institutionnelle ; elles ne sont pas présentées comme une règle réglementaire universelle.

Un seul destinataire actif est autorisé par défaut. Changer de banque exige une
préparation et une confirmation distinctes ; aucun dossier refusé n’est redistribué
automatiquement. Un retrait ne supprime pas une copie reçue. Une offre formelle ou
un décaissement déjà enregistré interdit de réutiliser ce même dossier pour chercher
un financement parallèle sans nouvelle demande et revue des engagements.

Les compléments et réponses bancaires sont déposés séparément, décodés dans le worker
isolé existant et non partagés tant que la communication n’est pas confirmée. Ils ne
modifient ni le manifeste initial ni l’attestation initiale. Une offre formelle et un
décaissement exigent une pièce, une référence et un responsable bancaire habilité.
Le décaissement ne peut être enregistré qu’après une offre formelle. Aucun calcul
financier historique n’est modifié par ces événements.

## Signature, clés et vérification

`cryptography==50.0.2` signe en Ed25519 le manifeste approuvé, les données de l’attestation
et l’empreinte de son PDF dans une enveloppe canonique. Un second manifeste signé
lie la sélection finale à la banque destinataire. L’archive contient les deux
manifestes et les deux signatures détachées ; les PDF sont sélectionnables et imprimables.
Le QR est généré localement avec ReportLab et pointe vers l’origine contrôlée du site.

Le modèle n’est **pas une signature PDF PAdES**, un cachet graphique ou une certification
par un prestataire de confiance. La signature est institutionnelle et cryptographique ;
la revue humaine et l’identité professionnelle du signataire sont consignées séparément.
Le contrat `TrustedSignatureProvider` est prévu pour une extension ultérieure ; aucun
prestataire certifiant tiers n’est installé ou annoncé comme opérationnel.

`CREDIT_PARTNER_KEYRING_FILE` référence un fichier serveur contenant :

- clé : `id`, `status` (`active`, `retired`, `revoked`), `purpose` (`demonstration`,
  `production`), `issuer_ids` et `public_key_base64` ;
- uniquement pour signer : `private_key_path`, PEM PKCS#8 Ed25519, permissions 600.

Il doit exister exactement une clé active du bon usage pour l’émetteur. Sans clé
applicable, l’émission signée échoue (503) : aucun repli vers une clé temporaire ou
un simple hash. La création d’une clé de développement est une action explicite :

```bash
.venv/bin/python -m scripts.partner_keys create-demo --key-id demo-2026 --issuer mon-institution
.venv/bin/python -m scripts.partner_keys retire --key-id demo-2026 --issuer mon-institution
# Révocation d’une clé compromise (conserver sa clé publique pour l’historique) :
.venv/bin/python -m scripts.partner_keys revoke --key-id demo-2026 --issuer mon-institution
```

La rotation de production doit préparer une nouvelle clé hors démarrage et remplacer
atomiquement le trousseau : nouvelle clé active, ancienne clé retirée mais conservée
pour vérifier l’historique. La CLI de démonstration n’est pas un dispositif HSM/KMS.
Sauvegarder les clés selon une stratégie de garde séparée de la base et de ses sauvegardes.
Les clés privées ne sont ni stockées dans les paquets ni transmises aux banques.

La page publique ne renvoie que l’émetteur, l’identifiant, la date et le statut. Elle
ne donne accès à aucun fichier. La banque authentifiée vérifie les signatures, les
empreintes, le rattachement et le statut. Une clé retirée peut vérifier l’historique ;
une clé révoquée bloque les nouveaux envois. La validité mathématique d’une signature
et la confiance juridique dans l’émetteur restent distinctes.

Exemples synthétiques et vérification hors ligne :

```bash
.venv/bin/python -m scripts.verify_partner_archive examples/partners/individuals-packet.demo.zip \
  --trusted-keyring examples/partners/public-keyring.demo.json --recipient demo-bank-institution
.venv/bin/python -m scripts.verify_partner_archive examples/partners/businesses-packet.demo.zip \
  --trusted-keyring examples/partners/public-keyring.demo.json --recipient demo-bank-institution
```

Le trousseau public d’une banque réelle doit être obtenu par une voie de confiance,
jamais accepté aveuglément depuis l’archive à vérifier. Les exemples sont signés par
une clé de démonstration et leurs QR renvoient à une session locale de test ; ils ne
constituent pas des attestations réelles actives. La vérification hors ligne démontre
l’intégrité, pas le statut de révocation actuel ni une confiance juridique.

## Outbox, reprises et garanties d’accès

La confirmation et la création de l’outbox sont dans la même transaction. Un choix
préparé n’est pas encore visible dans la boîte bancaire. `transmitted` rend le paquet
visible après le commit technique ; seul un agent bancaire peut produire `received`.
Un accusé HTTP, une signature valide ou un simple téléchargement ne vaut pas accord.

Les traitements utilisent une clé stable de transmission, un bail de 60 secondes,
trois tentatives automatiques et une temporisation exponentielle bornée. Deux reprises
manuelles au maximum sont possibles, avec motif et habilitation. Les tentatives sont
historiques. PostgreSQL utilise les verrous de lignes et le contrôle de version ; les
écritures suivent l’ordre dossier → transmission → outbox → partenaire. L’autorisation,
les empreintes, la politique, la banque et l’attestation sont revérifiées avant envoi
et avant publication dans la boîte du portail. Une modification concurrente peut
empêcher la publication sans changer les anciennes éditions.

Les adaptateurs futurs devront fournir une vraie idempotence côté destinataire et
gérer leurs délais, authentification et erreurs ; le simulateur ne prouve pas ces
capacités pour une banque réelle. Une interruption après un appel externe peut laisser
un résultat incertain ; un retrait ne garantit pas le rappel de données déjà reçues.
Le portail local a une disponibilité transactionnelle, sans appel externe.

Les webhooks sont réservés au compte du partenaire, avec HMAC-SHA-256, fenêtre de
cinq minutes, identifiant d’événement et séquence. Leur contrat normalisé, y compris
les valeurs par défaut, est signé sous la forme :
`timestamp + '.' + JSON_canonique(Webhook)`. Le secret est fourni hors dépôt par une
variable `CREDIT_PARTNER_WEBHOOK_*` référencée dans la configuration administrée.
Les doublons sont idempotents ; une séquence ancienne est enregistrée comme ignorée.
Une transition incohérente reçoit 409 plutôt qu’une régression du suivi.

L’historique métier privé conserve motifs, réserves, acteurs et dates. Les journaux
techniques conservent les identifiants utiles, jamais les documents ou corps financiers.
Les exports sont limités par acteur (30/minute par défaut), les paquets à 50 Mo, les
sources sélectionnées à 20, les revues à 20 par dossier et les compléments à 30 fichiers
par transmission. Les compléments sont limités à 5 Mo et 30 pages, avec les limites
supplémentaires du décodeur existant. Une analyse antivirus absente n’est jamais
présentée comme « fichier sain ». Les originaux, rendus et signatures restent privés.

L’approbation bancaire interne exige aussi une confirmation explicite du responsable
pour autoriser la prévisualisation privée du paquet prêteur par le demandeur. Avant
approbation, celui-ci ne peut pas télécharger ce paquet. Cette autorisation n’est ni
une publication sur Internet ni une transmission à une banque. Les règles existantes
de publication des rapports dans les autres écrans sont conservées.

## Principales API

Toutes passent par `/api` sur la passerelle et réutilisent sessions HttpOnly/CSRF ou
les identités techniques Bearer administrées. Aucun corps ne peut imposer un rôle,
une institution, un statut d’approbation ou une destination URL arbitraire.

| Opération | Route |
|---|---|
| Politique émettrice | `GET/PUT /partners/admin/policy` |
| Référentiel, test et activation | `/partners/admin/banks`, `/{id}/test`, `/{id}/activate`, `/{id}/status` |
| Suivi d’un dossier | `GET /{core}/{id}/banking` |
| Accès de l’équipe habilitée | `POST /{core}/{id}/banking/review-access` |
| Affectation initiale par un responsable | `POST /{core}/{id}/banking/assign-applicant` |
| Figer le paquet à examiner | `POST /{core}/{id}/internal-reviews` avec `Idempotency-Key` |
| Revue, décisions et attestation | `/internal-reviews/{id}`, `/{id}/decisions`, `/{id}/attestation` |
| Téléchargement privé de revue | `/internal-reviews/{id}/files/{file_id}` |
| Révocation | `POST /attestations/{id}/revoke` |
| Vérification publique minimale | `GET /public/attestations/{token}` |
| Préparer le choix | `POST /{core}/{id}/banking/previews` avec `Idempotency-Key` |
| Confirmer et suivre | `/transmissions/{id}`, `/{id}/confirm`, `/{id}/dispatch`, `/{id}/events` |
| Reprise et retrait | `/transmissions/{id}/retry`, `/{id}/withdraw` |
| Fichiers / archive privés | `/transmissions/{id}/files/{file_id}`, `/{id}/archive` |
| Boîte bancaire | `GET /bank/inbox` |
| Traitement bancaire | `/bank/transmissions/{id}`, `/{id}/events`, `/{id}/verify`, `/{id}/files/{file_id}`, `/{id}/archive` |
| Réponses et compléments | `POST /bank/transmissions/{id}/attachments`, `POST /transmissions/{id}/attachments`, `POST /transmissions/{id}/supplements` |
| Webhook authentifié | `POST /bank/webhooks/{partner_id}` |

Les routes de téléchargement des compléments utilisent `.../attachments/{id}`.
Le choix, l’ouverture de revue, les événements bancaires et les compléments exigent
une clé d’idempotence. Les actions de revue, confirmation et traitement incluent une
révision attendue. Les paramètres de test complets sont visibles dans
`tests/test_partners.py` et les modèles Pydantic dans `credit/partners/contracts.py`.

## Matrice de permissions

| Capacité | Demandeur titulaire | Analyste désigné | Responsable signataire | Administrateur émetteur | Agent banque destinataire | Responsable banque |
|---|---|---|---|---|---|---|
| Dossier / analyse interne | Ses droits existants, résultats publiés | Dossier explicitement accordé | Dossier explicitement accordé | Dossier explicitement accordé | Non | Non |
| Ouvrir une revue | Non | Oui | Oui | Oui | Non | Non |
| Approuver | Non | Non | Oui selon politique | Oui s’il est signataire | Non | Non |
| Émettre / révoquer | Non | Non | Oui | Oui | Non | Non |
| Choisir / confirmer / retirer | Oui | Non | Non | Non | Non | Non |
| Réception / étude / complément | Non | Non | Non | Non | Sa banque uniquement | Sa banque uniquement |
| Offre formelle / décaissement | Non | Non | Non | Non | Non | Oui avec référence et pièce |
| Administrer le partenariat | Non | Non | Non | Son institution uniquement | Non | Non |

Un administrateur n’a pas de droit implicite sur tous les dossiers. Les membres de
banques n’accèdent pas aux routes métier générales de l’émetteur : ils lisent uniquement
les versions explicitement transmises à leur institution. Les anciens liens restent
soumis aux mêmes contrôles d’objet ; un identifiant difficile à deviner ne les remplace pas.

## Avant toute activation réelle

Obtenir et vérifier pour chaque établissement : identité et représentants habilités,
accord de partenariat/mandat, périmètre et produits, pièces nécessaires, information et
accords de partage, règles de conservation, modalités de réception et de traitement,
comptes nominatifs et droits, points de contact et procédure d’incident. Pour une API :
spécification, environnement d’essai, authentification, destinations administrées,
idempotence, accusés, timeouts, reprises et webhook réels. Aucun de ces accès n’est inventé.

La BCEAO publie un cadre concernant les intermédiaires en opérations de banque :
[Textes d’application de la loi portant réglementation bancaire, édition décembre 2011](https://www.bceao.int/sites/default/files/2018-03/textes-application-de-la-loi-portant-reglementation_bancaire.pdf),
notamment l’instruction n°015-12/2010/RB (rubrique commençant à la page imprimée 25).
La source publique a été identifiée et consultée le 5 novembre 2026 ; sa présence ne
constitue pas une conclusion sur le droit actuellement applicable à Crédit PME.
Faire confirmer par les personnes compétentes la qualification du service, les
éventuelles formalités, les accords et la portée de l’attestation avant le réel.
Aucun statut d’intermédiaire, agrément ou accréditation n’est attribué automatiquement.

Avant exposition : recette de la banque, authentification renforcée selon les besoins,
configuration HTTPS/reverse proxy, sauvegarde/restauration incluant les nouvelles tables,
garde et rotation des clés, contrôle du stockage et conservation. Le processus isolé de
décodage/rendu n’est pas une isolation complète du système d’exploitation : le montage
des clés dans un même environnement nécessite une analyse de sécurité de déploiement ;
un service de signature séparé ou prestataire de confiance est une extension à qualifier.
Les paramètres Docker ont été validés comme configuration, pas comme déploiement réel.
Cette livraison ne constitue ni certification bancaire ni homologation de sécurité.
