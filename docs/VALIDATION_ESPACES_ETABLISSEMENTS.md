# Vérification des espaces établissements / admin

Documents et comptes uniquement synthétiques ; aucune banque réelle contactée.

- `pytest -q` : 327 réussis, 2 ignorés (concurrence PostgreSQL nécessitant TEST_DATABASE_URL), 2 avertissements de dépréciation Starlette/AnyIO ; 203,45 s.
- Après les dernières corrections de rendu et de périmètre : `pytest -q tests/test_institution_centres.py tests/test_partners.py` : 24 réussis, 2 ignorés, 77,51 s.
- `ruff check credit tests scripts migrations` : réussi.
- `cd frontend && npm run build && npm test` : 77 contrôles réussis (30 contrats, 44 transport/livraison, 3 frontières asynchrones).
- `python scripts/run_frontend_e2e.py --browser-test banking.cjs` : 39 contrôles de régression réussis, dont compléments, attestation et archive privée pour les deux noyaux.
- `python scripts/run_frontend_e2e.py --browser-test institution-centres.cjs` : 19 contrôles Chromium réussis sur particuliers et entreprises. Dernier résultat : `output/frontend/browser-ufxc1c0i/` (non versionné).

Le navigateur crée réellement un accès nominatif, active son invitation, se connecte, reçoit les deux dossiers, consulte rapports et PDF autorisés, confirme la réception, prévisualise les conditions calculées, enregistre une offre signée et un refus. Le demandeur reçoit les deux messages, télécharge réellement le PDF, vérifie sa signature. Accès d’une autre banque refusé et largeur mobile contrôlée.

Le PDF synthétique de trois pages a été extrait avec PyMuPDF puis chaque page rendue en image et inspectée : titre, conditions, calendrier, totaux, QR, références et pagination. Un exemplaire est conservé dans `examples/printing/bank-agreement.demo.pdf`. Son QR vise le serveur éphémère du test ; ce n’est pas un document utilisable pour un financement réel. Les captures desktop admin, banque, boîte client et mobile sont dans le répertoire du test.

Les tests de non-régression couvrent notamment : permissions administrateur, invitation unique et révocation de sessions, compte sans rôle libre, révisions périmées, archive, clés absentes, prévisualisation modifiée, envoi idempotent, refus sans PDF, échec de rendu sans message partiel, source d’analyse altérée, PDF altéré même avec hash de stockage modifié, signature, révocation et accès client/banque/public séparés.

Limites : pas de prestataire de signature certifiée, de notification SMS/e-mail ou de banque réelle configurés. Les contraintes de concurrence PostgreSQL ne sont pas validées par les tests SQLite ; elles requièrent la base de test dédiée documentée dans le README. La signature locale prouve l’intégrité selon les clés administrées, pas une certification juridique par un tiers.

## Refonte de l’administration et revue manuelle — 6 novembre 2026

- Suite complète backend : **328 tests réussis, 2 ignorés**, 2 avertissements Starlette/AnyIO, 196,94 s. Les deux tests ignorés restent les tests de concurrence PostgreSQL nécessitant une base dédiée.
- Tests ciblés `tests/test_institution_centres.py` : **10 réussis**. Nouveau contrôle : file administrative limitée à son institution, liste sans payload financier, prise en charge explicite, contrôle de version, création unique de l’habilitation et de son événement, refus des autres rôles et institutions.
- Régression Chromium `institution-centres.cjs` : **19 contrôles réussis** après séparation de la navigation admin ; offres signées, refus et réception client conservés.
- Chromium `admin-reviews.cjs` : contrôle des menus, redirection des anciennes URL demandeur, absence de nouvelle demande et de bloc de choix de banque, file particuliers/entreprises, pages sources réellement décodées, correction humaine persistée avec auteur, analyse historique et demande de compléments interne. Les captures desktop et mobile sont conservées dans `output/frontend/browser-*/` et exclues de Git.

L’inspection visuelle a conduit à raccourcir l’historique : seules les décisions de transcription sont affichées dans les cartes, au lieu de répéter toute l’extraction. Les sources brutes restent consultables séparément. Le compte admin conserve sa déconnexion et ne comporte plus les cartes de projets demandeur. Les fichiers originaux sont accessibles à partir des références `source_id` des pages, même lorsque le dépôt n’expose pas de tableau `sources` distinct.

Dernière vérification de la refonte : **26 contrôles navigateur admin réussis**, incluant l’accès aux originaux ; **78 contrôles frontend** réussis (30 contrats, 45 livraison/transport et 3 frontières asynchrones). Le formulaire de correction et sa page source sont disposés côte à côte sur ordinateur et empilés sur mobile. La prise en charge de la revue ne modifie pas les faits financiers ni les analyses historiques.
