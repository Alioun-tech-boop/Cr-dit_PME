# Accueil public et entrée dans Crédix

Trois documents indépendants utilisent le même domaine :

- `/` : présentation publique, photos et vidéos locales de finance, deux parcours,
  méthode et liens Visiter / Se connecter. Aucun chargement de dossiers privés.
- `/login.html` : sections de connexion et de création de compte par e-mail ou téléphone. La connexion utilise `/auth/login`, l’inscription `/auth/register`. Une session
  existante est reprise ; après connexion, destination interne fixe vers
  `/platform.html#overview`, ou `#bank-inbox` pour les rôles bancaires authentifiés.
- `/platform.html` : interface existante et ses parcours. Sans session, le bandeau
  visiteur explique les limites et propose la connexion. Les API vérifient toujours
  les droits ; le paramètre `visiteur=1` ne confère aucune permission.

Les anciens liens `/#profile`, `/#documents`, etc. sont redirigés côté navigateur
vers le fragment correspondant de `platform.html`. Les ancres de présentation
restent sur l’accueil public. Les noms de routes métier restent inchangés.

Le formulaire n’enregistre aucun mot de passe ni jeton dans localStorage. Il ne
permet pas de choisir un rôle ou une institution. Le cookie HttpOnly et la
protection CSRF sont toujours fournis par le backend. Les erreurs de connexion
et réseau permettent de réessayer, sans dévoiler les réponses internes.
Aucun paramètre de retour externe n’est accepté.

Les vidéos utilisent le moteur local `home-videos.js`, avec pause, réduction des
animations et prise en compte de l’économie de données. Aucune plateforme vidéo
externe ni nouveau fournisseur d’identité n’a été ajouté.

## Assemblage et vérifications

```bash
cd frontend
npm ci
npm run build
npm test
cd ..
.venv/bin/pytest -q tests/test_web_integration.py tests/test_security_audit.py
.venv/bin/python scripts/run_frontend_e2e.py --browser-test public-home.cjs
.venv/bin/python scripts/run_frontend_e2e.py
```

Le lanceur navigateur prépare une base et des identités entièrement synthétiques,
puis vérifie les parcours dans Chromium. Il arrête le serveur après les essais.
Les captures et journaux restent sous `output/frontend/`, hors Git.
L’assemblage versionne séparément les scripts et CSS des trois pages.

Le démarrage reste `python -m credit.security.entrypoint` avec les configurations
existantes. Render sert les trois pages sans nouvelle route backend ni migration.
Pour Netlify, le répertoire publié reste `frontend/dist` et les réécritures de
passerelle API/session restent nécessaires. Le contrôle d’accès de l’hébergement
et l’authentification métier restent distincts.

Les coordonnées restent déclarées et non vérifiées tant qu’aucun fournisseur d’e-mail/SMS et parcours de code n’est configuré. Voir [la politique d’inscription](../../docs/INSCRIPTION_DEMANDEURS.md).
