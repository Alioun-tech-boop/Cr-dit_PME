# Espaces établissements et administration — Crédix

Cette version conserve les deux noyaux financiers et les éditions transmises. Aucun partenariat réel, signature certifiée par un tiers ou accord bancaire n’est créé au démarrage.

## Parcours disponibles

- Administrateur de l’institution : `/platform.html#admin-centre/overview` (activité) et `#admin-centre/partners` (banques et microfinances).
- Agent bancaire : connexion nominative puis `#bank-inbox`, `#bank-history`. Seules les transmissions effectivement partagées avec son établissement sont consultables.
- Responsable bancaire : mêmes accès, décision favorable ou refus motivé. Une offre requiert des conditions complètes et une prévisualisation du coût calculée par le serveur.
- Demandeur : `#inbox`, messages, téléchargement PDF, aperçu imprimable et contrôle de signature.

Le dossier reçu comporte les éditions et justificatifs **explicitement autorisés** lors du partage. Le rapport détaillé n’est lisible que si sa catégorie a été autorisée. Les notes internes sont exclues. Le hash de l’analyse est rapproché du manifeste approuvé avant lecture.

## Comptes et établissements

L’administrateur crée un partenaire en préparation, renseigne les produits, périmètres et catégories de pièces, teste le portail puis conserve les références de partenariat, représentants, partage et revue juridique avant activation. Une modification du profil impose une nouvelle vérification et activation. L’archivage suspend les nouvelles opérations et révoque les accès gérés ; les transmissions historiques restent conservées.

Les comptes nominatifs sont `bank_agent` (consultation, réception, étude, complément) ou `bank_manager` (décision, émission, révocation). Le rôle et le rattachement sont attribués côté serveur. Une invitation confidentielle expire après 24 heures et ne peut être utilisée qu’une fois. Le titulaire choisit son mot de passe ; aucun mot de passe existant n’est révélé. Réinitialiser, modifier les droits ou désactiver révoque les sessions. La suppression est logique pour préserver les auteurs historiques. Aucun e-mail ou SMS n’est envoyé automatiquement : le lien doit être remis au représentant vérifié par un canal approprié.

## Offre et signature

Le responsable saisit montant, devise, taux nominal, dates, échéances, frais, assurance chiffrée, garanties, conditions de décaissement, remboursement anticipé, retard, validité et identité professionnelle. Les montants utilisent `Decimal`. Le taux saisi en pourcentage est converti par le serveur. Le générateur réutilise la convention mensuelle du noyau ; un échéancier explicite peut être fourni avec contrôle du capital et des dates.

Le coût comprend intérêts, frais périodiques, frais initiaux et assurance chiffrée. Les frais initiaux ne sont pas automatiquement financés. Aucun TAEG réglementaire n’est revendiqué. L’enregistrement favorable crée atomiquement un PDF immuable, une réponse bancaire, un événement et un message client ; un refus crée un message sans fausse attestation. Une erreur PDF empêche leur création. L’idempotence empêche un double enregistrement après reprise réseau.

Le PDF porte le titre « Attestation d’accord de financement », ses conditions, l’échéancier, ses identifiants et un QR de vérification. Il ne prouve ni l’acceptation du demandeur ni le décaissement. La signature **Ed25519 détachée** couvre le manifeste contenant son empreinte et les termes. Elle ne constitue pas une certification électronique par un prestataire de confiance. Une émission signée sans clé applicable est refusée (503). Le choix explicite d’une édition non signée reste visible comme **NON SIGNÉE**.

`CREDIT_PARTNER_KEYRING_FILE` désigne un registre privé administré, documenté dans `TRANSMISSION_BANCAIRE.md`. Chaque clé bancaire doit porter l’identifiant bancaire dans `issuer_ids` ; en production, elle doit également porter l’identifiant exact du partenaire dans `partner_ids`. Les fichiers privés PEM doivent avoir des permissions 0600. Conserver les clés publiques historiques pour vérification ; utiliser `retired` pour la rotation et `revoked` pour une compromission. Aucune clé de production n’est générée automatiquement. Une clé de démonstration ne fonctionne pas en production.

La révocation d’une offre conserve le PDF original et prévient le client. La page publique `/verify-bank-agreement.html?id=...` expose uniquement émetteur, identifiant, date, état et absence de certification tierce ; aucune identité client ni montant.

## API principales

Toutes les routes privées ci-dessous sont sous `/api` derrière la session HttpOnly et le CSRF existants (ou l’authentification Bearer serveur autorisée).

| Route | Droit |
|---|---|
| GET `/institution-admin/metrics?days=30` | Administrateur, institution propre |
| PATCH/DELETE `/institution-admin/partners/{id}` | Administrateur propriétaire, version attendue |
| GET/POST `/institution-admin/partners/{id}/accounts` | Administrateur propriétaire |
| PATCH `/institution-admin/accounts/{id}` | Administrateur propriétaire, révision attendue |
| POST `/institution-admin/accounts/{id}/reset` | Administrateur propriétaire |
| POST `/auth/activate` (hors `/api`) | Invitation unique, origine vérifiée |
| GET `/bank/workspace`, `/bank/inbox` | Agent ou responsable, établissement propre |
| GET `/bank/transmissions/{id}/analysis` | Banque destinataire, rapport autorisé |
| POST `/bank/transmissions/{id}/decision-preview` | Responsable bancaire |
| POST `/bank/transmissions/{id}/decision` | Responsable, révision + Idempotency-Key |
| GET `/inbox`, POST `/inbox/{id}/read` | Demandeur destinataire |
| GET `/agreements/{id}/pdf`, `/preview`, `/signature` | Demandeur destinataire |
| GET `/bank/agreements/{id}/pdf`, `/preview`, `/signature` | Banque destinataire |
| POST `/bank/agreements/{id}/revoke` | Responsable bancaire |

## Lancement et vérifications

Depuis la racine du projet, après installation des dépendances selon le README :

```bash
.venv/bin/alembic upgrade head
cd frontend && npm ci && npm run build && npm test
cd ..
.venv/bin/python -m uvicorn credit.web.application:app --host 127.0.0.1 --port 8000 --no-access-log
```

Configurer `DATABASE_URL`, `CREDIT_AUTH_FILE`, `CREDIT_WEB_ORIGIN` et les restrictions de l’environnement selon `.env.example`. Ne pas utiliser `credit.api:app` seul pour les pages et sessions navigateur.

Démonstration automatisée isolée, sans banque réelle ni notification externe :

```bash
.venv/bin/pytest -q tests/test_institution_centres.py tests/test_partners.py
.venv/bin/python scripts/run_frontend_e2e.py --browser-test institution-centres.cjs
```

Cette commande prépare des dossiers synthétiques, des approbations, un partage consenti et une clé bancaire de démonstration, lance Chromium et arrête le serveur. Les PDF, captures, journaux et comptes synthétiques sont sous `output/frontend/browser-*/`, exclu de Git. Chromium doit être installé à `/usr/bin/chromium`.

## Mesures et limites

Le centre admin agrège les données de **son institution** : dossiers, analyses dans la période, transmissions, offres/refus, comptes et échecs. Le nombre de dossiers est un stock ; la série quotidienne porte sur les analyses horodatées. Ces compteurs ne sont ni des taux de défaut ni une validation bancaire.

Avant utilisation réelle : accords et représentants vérifiés, politiques de conservation, clés bancaires provisionnées et protégées, portée juridique du document validée. Aucun prestataire de certification tierce, KYC bancaire automatique, envoi automatique de courriel ou connexion bancaire externe n’est configuré par ce parcours.

## Administration dédiée et vérifications manuelles

La navigation administrateur contient uniquement **Activité**, **Vérification des dossiers**, **Établissements & accès**, ainsi que son compte et ses paramètres. Les liens de demande de financement, accompagnement, choix de banque, vidéos et simulations du demandeur ne sont pas montés dans cet espace. Un accès direct à leurs anciennes URL renvoie l’administrateur vers son centre d’activité. Le compte conserve sa déconnexion réelle, sans cartes du parcours client.

`#admin-centre/reviews` affiche une file paginée de l’institution, filtrable entre particuliers et entreprises. Elle expose uniquement les métadonnées de suivi. **Prendre en charge et examiner** contrôle la version puis crée une habilitation explicite `CaseGrant` pour l’admin, avec événement `admin_review_claimed`. Aucune habilitation sur une autre institution n’est possible. Cette prise en charge n’approuve ni les données ni le crédit.

Dans le dossier :

1. **Données du dossier** : données enregistrées, sections repliables, montants et inconnus tels que reçus.
2. **Pièces & transcriptions** : pages autorisées, agrandissement, originaux téléchargeables, états séparés du dépôt, qualité, OCR, revue et authenticité. Une correction exige le choix d’un champ, une valeur, une ou plusieurs références sources, une justification et une confirmation humaine. La révision est contrôlée et l’auteur et la date sont conservés. Aucune valeur n’est automatiquement envoyée au scoring.
3. **Résultats d’analyse** : choix d’une analyse historique, sous-analyses et sources du serveur, sans calcul navigateur.
4. **Revue & approbation** : constitution d’un paquet versionné avec sélection explicite des pièces, demande de compléments ou décision interne selon les habilitations et la politique existantes. Une clé et une politique applicables restent nécessaires pour émettre une attestation. Une décision bancaire ne peut pas être prise ici.

Nouvelles opérations serveur : `GET /api/institution-admin/review-cases?core=individuals&limit=30&offset=0` et `POST /api/institution-admin/review-cases/{id}/claim` avec `expected_revision`. Toutes les lectures et mutations ultérieures réutilisent les contrôles d’objet existants. Aucune migration supplémentaire n’est nécessaire.

Vérification synthétique dédiée :

```bash
.venv/bin/python scripts/run_frontend_e2e.py --browser-test admin-reviews.cjs
```

Le test prépare les deux noyaux et des relevés synthétiques réellement extraits, puis vérifie menus, protection des URL, prise en charge, consultation des sources, correction humaine, analyses, compléments et largeur mobile. Aucun compte ou dossier réel n’est modifié par ce test.
