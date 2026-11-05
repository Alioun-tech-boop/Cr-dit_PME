# Inscription par e-mail ou téléphone

`POST /auth/register` crée un compte demandeur persistant. Le formulaire et le
contrat ne contiennent ni rôle, ni institution, ni statut de vérification.
`CREDIT_SIGNUP_INSTITUTION_ID` doit être défini par l’opérateur ; vide ou absent,
l’inscription retourne 503. Ce paramètre affecte les nouvelles inscriptions,
sans modifier le périmètre des comptes déjà créés.

L’accès obtenu permet uniquement les opérations déjà autorisées au rôle
`applicant`, avec contrôle du propriétaire et de l’institution à chaque dossier.
Il ne donne aucun droit d’analyse interne, d’approbation, de publication ou
d’accès bancaire. Les comptes existants du registre serveur restent utilisables.
Les nouveaux comptes utilisent uniquement les sessions opaques HttpOnly, avec
CSRF pour les écritures ; aucun jeton Bearer partagé n’est créé au navigateur.

- E-mail : normalisé en minuscules, format contrôlé, longueur maximale 100.
- Téléphone : format international `+indicatif` ; un numéro burkinabè de huit
  chiffres est préfixé explicitement par `+226`. Les autres numéros locaux ne
  reçoivent pas un pays inventé.
- Mot de passe : 12 à 128 caractères, confirmation, Argon2id avec la bibliothèque
  existante, concurrence de hachage bornée.
- Coordonnées : `contact_status=not_verified`. Aucun e-mail ou SMS n’est envoyé,
  aucun code ni vérification de propriété n’est simulé. La connexion par mot de
  passe ne certifie ni l’identité, ni la propriété des coordonnées déclarées.
- Réponse identique 202 pour une adresse nouvelle ou existante ; le coût de
  hachage est conservé et un compte existant n’est jamais réinitialisé.
- Limite locale : cinq demandes par heure par IP et par coordonnée hachée. La
  protection ne remplace pas une limite partagée pour plusieurs instances.

La table `web_registrations` relie le compte à son institution attribuée par le
serveur, au canal déclaré et à la date. Les coordonnées restent privées. La
modification du profil ne change ni le rôle ni l’identifiant de connexion.

## Installation

```bash
python -m alembic upgrade head  # migration 0009, rôle administratif distinct
export CREDIT_SIGNUP_INSTITUTION_ID='<institution-configurée>'
python -m credit.security.entrypoint
```

Après migration, accorder les permissions applicatives sur la nouvelle table
avec la procédure administrative existante. En production, ne pas donner les
droits de création de rôles ou de migration au compte applicatif permanent.
Le déploiement Render utilise temporairement le provisionnement administratif
explicite déjà livré, puis retire son fichier et son activation après contrôle.

```bash
.venv/bin/pytest -q tests/test_registration.py tests/test_web_integration.py tests/test_deployment.py
.venv/bin/python scripts/run_frontend_e2e.py --browser-test public-home.cjs
```

Les comptes des tests sont synthétiques et isolés. Pour un parcours de
vérification des coordonnées, il reste à choisir et configurer un fournisseur
SMTP/SMS, les codes à usage unique et la récupération de compte. Aucun de ces
services n’est annoncé comme opérationnel ici.
