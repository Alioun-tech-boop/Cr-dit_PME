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
