# Vérifications de la transmission bancaire

Vérifications exécutées le 5 novembre 2026, uniquement avec dossiers, institutions,
banques, clés et destinataires synthétiques. Aucun message ni document envoyé à une
banque réelle. Les fichiers de travail sont dans `output/partners/` et
`output/frontend/`, exclus de Git.

| Vérification réellement exécutée | Résultat final |
|---|---|
| Référence avant modifications : `.venv/bin/pytest -q` | 288 réussis, 2 avertissements de dépréciation |
| Suite complète finale : `.venv/bin/pytest -q` | **303 réussis, 2 ignorés**, 2 avertissements, 167,21 s |
| Parcours partenaires sur PostgreSQL isolé : `TEST_DATABASE_URL=…/credit_test .venv/bin/pytest -q tests/test_partners.py` | **17 réussis**, 2 avertissements, 74,48 s |
| `.venv/bin/python -m scripts.run_frontend_e2e --browser-test banking.cjs` | **39 contrôles Chromium réussis**, aucune erreur JavaScript |
| Régression : `.venv/bin/python -m scripts.run_frontend_e2e` | **54 contrôles navigateur existants réussis**, menus et centrage mobile préservés |
| Depuis `frontend/` : `npm test` | 30 contrôles de contrats, 43 de livraison/transport et 3 de frontières asynchrones réussis |
| Depuis `modules/credit_pme_pdf/` : `../../.venv/bin/python -m unittest discover -s tests -v` avec le modèle OCR français configuré | **167 tests réussis**, 6,99 s |
| `.venv/bin/ruff check credit tests scripts migrations` | Aucun problème signalé |
| `git diff --check` | Aucun problème signalé |
| Préparateur `.venv/bin/python -m scripts.prepare_partner_demo …` | Base locale isolée, migration 0008, comptes privés, clé et banque fictives effectivement créés |
| Vérification hors ligne des deux archives dans `examples/partners/` | Signatures et empreintes vérifiées avec le trousseau public de démonstration et le destinataire attendu |
| `docker compose -f compose.yaml -f compose.partners.yml config --quiet` avec un répertoire explicitement configuré | Configuration acceptée ; aucun déploiement de conteneur ni test de connexion bancaire réel annoncé |

Les deux tests ignorés dans SQLite sont précisément les contrôles PostgreSQL de
concurrence. Ils ont été exécutés et réussis avec PostgreSQL dans la suite partenaire.
La base `credit_test` est dédiée aux essais ; aucune base client n’a été supprimée.

Les premiers essais ont révélé puis permis de corriger l’ordre d’insertion des
événements sous contraintes FK PostgreSQL, l’accès du demandeur à son historique de
transmission et des synchronisations de navigation dans le test navigateur. Les
résultats finaux ci-dessus sont ceux obtenus après correction, sans suppression ou
affaiblissement des contrôles métier.

## Couverture

- Analyse sans approbation et accès direct : aucun choix/transfert autorisé.
- Rôles, séparation demandeur/signataire, double validation, auteur d’analyse distinct,
  révisions périmées et absence de clé de signature.
- Modification de dossier ou de pièce : approbation inutilisable, ancienne édition
  conservée, nouvelle analyse exigée.
- Banque inactive, configuration et catégories non admises, URL arbitraire refusée.
- Consentement absent ou incohérent, opérations idempotentes, nouvelle tentative,
  exécution effective du worker en ligne de commande.
- Réception technique distincte de réception métier et de décision.
- Accès croisés entre demandeurs et banques, téléchargements et archives privés.
- Altération de fichier/manifeste, expiration, révocation et retrait de clé.
- Page publique limitée à quatre champs, sans identité du demandeur ni montants.
- Webhook falsifié, expiré, répété ou dans le désordre.
- Compléments non partagés au simple dépôt ; confirmation séparée et réponse bancaire
  autorisée ; offre formelle distincte de l’offre conditionnelle et de l’analyse.
- Retrait avant/après disponibilité bancaire, sans promesse d’effacement à distance.
- Deux workers concurrents ne publient qu’une fois ; une modification du dossier
  pendant le traitement empêche sa publication dans la boîte bancaire.

## Documents réellement produits

Les deux attestations PDF de démonstration comptent trois pages chacune, avec texte
sélectionnable, QR, identifiants, versions, portée, réserves, clé et empreintes. Leurs
planches de pages ont été inspectées visuellement. Les rapports prêteurs comprennent
10 pages (particulier) et 12 pages (entreprise) ; leur texte a été extrait et contrôlé.
Les archives comprennent les fichiers sélectionnés, les deux manifestes et les deux
signatures détachées. Aucun fichier privé de clé ou mot de passe n’y est inclus.

Les QR des exemples pointent vers la session locale de test ; cette session n’est pas
une banque accessible publiquement. L’intégrité hors ligne reste démontrable avec le
trousseau public fourni ; le statut en ligne nécessite la base et le serveur émetteurs.

## Limites restant à lever avant le réel

Aucune API bancaire externe ni prestation de signature électronique certifiée n’a été
configurée. Les accords, représentants, mandat/périmètre juridique, partage de données,
exigences documentaires, clés de production et modalités opérationnelles doivent être
obtenus et vérifiés avec chaque banque. Le portail permet une réception sans API externe,
mais ne crée pas en lui-même un partenariat ou une autorisation réglementaire.

L’administration avancée et la sélection des références de sources restent techniques.
Les notifications sont internes à l’application, avec actualisation ; pas d’email/SMS
ni de notification poussée externe. L’isolation des sous-processus ne remplace pas une
qualification du déploiement et de la garde des clés. Le Docker optionnel a été validé
en configuration uniquement. Cette validation ne vaut pas certification de sécurité,
agrément BCEAO ou validation juridique de la portée de l’attestation.
