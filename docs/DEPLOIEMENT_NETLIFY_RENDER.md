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
