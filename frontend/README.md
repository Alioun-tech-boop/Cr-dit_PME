# Frontend Crédit PME connecté

Design fourni conservé dans `src/styles`, ressources locales et scripts dans `dist`.
La passerelle Python sert le site, `/api` et `/auth` sur une seule origine.
Aucun jeton technique dans les ressources publiques.

Voir le guide complet [FRONTEND_BACKEND.md](../docs/FRONTEND_BACKEND.md) : installation,
comptes, politiques documentaires, revue, publication, PDF, tests et hébergement.

```bash
npm ci
npm test
npm run build
```

Depuis la racine : `uv run python -m scripts.run_frontend_e2e` lance les parcours
réels dans Chromium sur une base et des identités synthétiques isolées.
Les calculs sont exclusivement ceux des deux noyaux Python. Les fichiers de
`docs/` décrivant l’audit initial du frontend sont des constats historiques ;
le guide d’intégration à la racine fait référence pour le fonctionnement actuel.
