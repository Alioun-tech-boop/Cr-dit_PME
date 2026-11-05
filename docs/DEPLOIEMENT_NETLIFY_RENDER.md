# Déploiement Netlify / Render

Le frontend reste statique, avec sessions HttpOnly et CSRF à la même origine.
Les API métier ne sont pas ouvertes anonymement pour faciliter le déploiement.

## Netlify

Relier le dépôt GitHub et sa branche `main`, conserver `netlify.toml` à la racine.
La commande assemble `frontend/dist` puis crée les routes de passerelle.
Définir `CREDIT_BACKEND_ORIGIN=https://<service>.onrender.com` dans les variables
**Builds** du site ; ce paramètre public n’est pas une clé d’authentification.
Les chemins `/api/*`, `/auth/*` et `/health` sont proxyfiés vers Render.
Ne pas remplacer `runtime-config.js` par une URL d’API externe.

```bash
cd frontend
npm ci
npm run build
cd ..
CREDIT_BACKEND_ORIGIN=https://<service>.onrender.com node scripts/build_netlify_routes.mjs
# Si le CLI Netlify est installé et authentifié :
netlify deploy --prod --dir frontend/dist
```

Le fichier `_redirects` est produit au build, sans secret. Les déploiements
manuels seront remplacés par le prochain build Git lorsque celui-ci est activé.

## Render

Le fichier `render.yaml` décrit un nouveau service Docker. Le plan gratuit
sert uniquement à vérifier l’installation : veille et ressources limitées,
sans engagement de disponibilité. Il ne constitue pas un hébergement de
production validé. Aucun autre projet existant ne doit être adopté ou modifié.

Prérequis à fournir avant démarrage :

- PostgreSQL persistant, sauvegardé, et rôle applicatif sans droits superuser,
  createdb, createrole ou bypassrls.
- `DATABASE_URL` au format `postgresql+psycopg://...?...&sslmode=verify-full`,
  avec chaîne de confiance TLS vérifiée. Ne pas utiliser SQLite éphémère.
- Migrations exécutées séparément avec le rôle administratif :
  `python -m alembic upgrade head` (révision attendue : `0008`).
- Fichier secret Render `credit-auth.json`, disponible à
  `/etc/secrets/credit-auth.json`, accessible au processus et permissions 0600.
  Il contient les identités et habilitations réelles, jamais les comptes de démo.
  Si le montage Render ne permet pas ces permissions, adapter le provisionnement
  privé avant activation ; ne pas enlever le contrôle de permissions.
- `CREDIT_WEB_ORIGIN` : URL HTTPS exacte du site Netlify.
- `CREDIT_ALLOWED_HOSTS` : hôtes explicites Render et Netlify, sans `*`.
- `CREDIT_TRUSTED_PROXY_IPS` : réseaux/adresses de proxy Render vérifiés, sans `*`.
  Vérifier le schéma HTTPS observé à travers Netlify et Render.
- Comptes navigateur provisionnés par l’opérateur via
  `python -m scripts.provision_web_user --actor-id <id> --username <nom>`.

Le port utilise `PORT` fourni par Render, ou 8000 localement.
Les contrôles de production refusent une configuration incomplète.
Aucune clé temporaire d’attestation n’est créée au démarrage. Les transmissions
réelles restent désactivées jusqu’aux accords partenaires et clés configurées.
Un worker outbox séparé peut ensuite exécuter `python -m scripts.partner_worker`
avec les mêmes frontières d’accès, base et secrets privés.

## Vérifications après publication

Vérifier `/health` sur Render et à travers Netlify, puis `/auth/session`
(réponse 401 sans session). Tester connexion, CSRF, reprise du brouillon et droits
avec des comptes autorisés. Vérifier PDF/OCR et téléchargements privés ; aucune
réussite n’est déduite du seul succès du build. Un proxy Netlify est limité en
durée : les traitements longs nécessitent le worker prévu, sans délais illimités.

L’accès au site Netlify et les sessions métier Crédit PME restent distincts.
Ne pas affaiblir la protection du site ni partager de jeton technique au navigateur.

## État constaté le 5 novembre 2026

- Dernière version applicative poussée sur `main` dans le dépôt privé
  `Alioun-tech-boop/Cr-dit_PME`.
- Render : espace `My Workspace` confirmé. Aucun service Crédit PME existant.
  Tentative de création du Blueprint `credit-pme` depuis `main` : réponse 400,
  « the repository, branch, or Blueprint file could not be accessed ».
  Le fichier et la branche étant présents sur GitHub, vérifier l’autorisation
  du dépôt privé dans l’intégration GitHub de Render, puis réessayer.
  Aucun service ni Blueprint déployé n’a été confirmé.
- Netlify : aucun projet Crédit PME identifié. L’intégration disponible gère
  les projets mais ne propose pas de publication ni de liaison au dépôt.
  Aucun jeton CLI n’est configuré. Le propriétaire a indiqué ne pas pouvoir
  fournir ce jeton. Alternative : importer le dépôt depuis l’interface Netlify
  avec l’intégration GitHub, puis appliquer la configuration ci-dessus.
  Aucun déploiement Netlify n’est annoncé comme effectué.
- Les autres projets Netlify et Render restent inchangés. Le dépôt reste privé.
- Vérifications exécutées : assemblage frontend réussi, 76 contrôles frontend,
  65 tests backend ciblés réussis (2 avertissements de dépréciation), Ruff réussi.
  Pas de vérification bout en bout sur un hébergement distant : aucun nouveau
  service n’a pu être publié.

### Reprise après passage du dépôt en public

Visibilité GitHub vérifiée : `PUBLIC`. Render peut désormais lire le dépôt.
Blueprint créé et planifié : `exs-dbmastec6qcc738fvrf0` (espace My Workspace).
Le plan propose uniquement un nouveau service Docker gratuit à Francfort,
`credit-pme-api-62j3`, sans modifier les autres services.

Plan à compléter :
https://dashboard.render.com/blueprint/exs-dbmastec6qcc738fvrf0/sync/exe-dbmastmc6qcc738fvs10

État constaté : `planned`, non appliqué, non déployé. Render demande
`DATABASE_URL`, `CREDIT_ALLOWED_HOSTS`, `CREDIT_WEB_ORIGIN` et
`CREDIT_TRUSTED_PROXY_IPS`. Le registre privé d’authentification et les migrations
administratives restent également requis. Ne pas renseigner des valeurs fictives
pour contourner les contrôles de démarrage.

### Déploiement effectué via l’API Render

Le backend et le frontend de même origine sont disponibles à :
https://credit-pme-api-62j3.onrender.com

Ressources créées : service `srv-dbmb0o1srm7s73fjol3g`, base PostgreSQL 16
`dpg-dbmattgae00c738ru7og-a`, région Francfort, plans gratuits. La base expire
le 5 décembre 2026 : choisir un plan adapté et des sauvegardes avant tout usage
réel. Aucun service d’un autre projet n’a été modifié.

Le démarrage vérifie toujours PostgreSQL TLS `verify-full`, les droits réduits
et la révision Alembic. Les connexions externes PostgreSQL sont autorisées
uniquement depuis les deux plages de sortie Render déclarées pour ce service ;
elles sont partagées avec les autres services Render de la région. Les mots de
passe et les habilitations PostgreSQL restent nécessaires.

Le registre monté `credit-auth.json` est copié dans un répertoire temporaire 0700,
avec fichier 0600, avant les contrôles de production. `CREDIT_AUTH_SOURCE_FILE`
indique ce montage. Il ne contient aucun mot de passe utilisateur en clair.
Le compte initial d’exploitation possède un mot de passe aléatoire Argon2id,
sans réutilisation des comptes de démonstration. Son périmètre technique est
`credit-pme-operator` ; il ne représente pas une banque partenaire activée.
Les accès initiaux sont conservés dans `.local/render-deploy/owner.private.json`,
exclu de Git, permissions 0600. L’identité expire à 30 jours ; organiser son
renouvellement et le provisionnement des vrais utilisateurs habilités.

Le provisionnement initial `python -m scripts.bootstrap_render` exige
explicitement `CREDIT_RENDER_BOOTSTRAP=true` et un fichier secret administratif.
Il applique les migrations et crée le rôle `credit_application`, sans modifier
les comptes déjà présents. Le fichier administratif et ce paramètre sont retirés
du service après installation. Les migrations suivantes restent une opération
administrative distincte ; ne pas réintroduire le secret administratif dans le
service permanent.

Vérifications exécutées sur le service distant : 22 contrôles HTTP réussis,
comprenant connexion, CSRF, sessions, dossiers synthétiques particuliers/PME,
analyses v2, PDF et refus des téléchargements anonymes. Connexion et liste des
dossiers également vérifiées dans Chromium distant, sans erreur JavaScript.
Localement : 66 tests ciblés réussis, avec deux avertissements de dépréciation.

Cette mise en ligne Render ne constitue pas une publication Netlify ni une
validation de production. Signature institutionnelle, partenaires bancaires,
worker permanent et exploitation de production restent à configurer selon leurs
procédures respectives. Révoquer la clé API partagée dans la conversation après
les opérations ; elle n’a été enregistrée ni dans Git ni dans l’image Docker.
