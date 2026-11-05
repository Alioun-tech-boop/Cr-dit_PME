# Crédit PME — préparation de la mise en production

Version 1.0.0-rc.1 · 4 novembre 2026

## Changements livrés

Photos sans contour, texte en graisse 700 réelle avec Manrope locale, navigation animée avec option active centrée, historique précédent/suivant, pages Profil et Paramètres. Les animations respectent la réduction des mouvements. Les préférences de mouvement, densité et taille du texte sont fonctionnelles et persistantes.

Tous les champs sont enrichis d’une aide contextuelle accessible au clic et au clavier : identité, projet, montants, flux, dettes, comptabilité, garanties, documents et recadrage. Les aides expliquent la donnée attendue ; les indications secondaires encombrantes sont retirées du formulaire. Les fenêtres restituent le focus à leur fermeture. Un lien d’évitement permet d’accéder au contenu.

Les quatre feuilles de style sont assemblées dans une seule ressource. Les scripts et le CSS portent une empreinte de contenu dans leur URL. Photos et polices sont locales. Les exemples financiers et rapports fictifs sont exclus de la publication. La politique CSP de la page limite les ressources à la même origine ; les règles `_headers` doivent également être vérifiées sur l’hébergement final avant ouverture au public.

## Validation exécutée

`npm test` : 24 contrôles de parcours/contrats et 38 contrôles de livraison/transport, plus analyse de syntaxe des huit scripts. Contrôles notamment sur les erreurs 403/204, réponses malformées, protection CSRF, délais d’attente, exclusions des fixtures, configuration, empreintes de cache et dépôt des pièces. Les doubles envois automatiques sont évités lorsqu’un résultat réseau est incertain ; une réconciliation serveur est alors requise.

`python tests/verify_backend.py /workspace/scratch/fd53880bebef/backend-audit` : 20 contrôles des noyaux réels au commit `a22b7ab43b5836bf4796798b2bd013ab5959055e`. Ceci ne constitue pas une exécution complète de l’API FastAPI ni de ses tests d’intégration.

Vérification dans le navigateur : navigation, restauration des préférences après rechargement, aides de formulaire et restitution du focus. La graisse calculée des champs contrôlés est 700. Contrôle à 375 px utiles : la page Paramètres ne présente aucun débordement horizontal global. Les pages conservent leurs styles adaptatifs ; une recette multi-appareils avec lecteurs d’écran reste à réaliser sur l’environnement final.

## Contrats à fournir par le serveur

Le serveur métier doit être exposé derrière la même origine HTTPS, par un BFF ou proxy authentifié. Ne jamais incorporer de jeton durable dans le frontend.

| Configuration | Contrat attendu |
| --- | --- |
| `apiBaseUrl` | Racine des routes crédit auditées ; contrôle des droits côté serveur. |
| `sessionEndpoint` | GET renvoyant `{user:{id,displayName,email,telephone}}` ; 401 si session absente. |
| `csrfTokenEndpoint` | GET renvoyant `{token}` ; jeton attaché aux mutations avec la session. |
| `profileEndpoint` | PATCH authentifié, validation des données et réponse avec `{user:{id,...}}`. |
| `loginUrl` | Point d’entrée de connexion de la même origine. |
| `logoutUrl` | POST de déconnexion avec protection CSRF. |
| `publishedAssessmentEndpoint` | Réservé à une future projection des rapports publiés ; non branché dans cette version. |

Le dépôt implémente création/mise à jour de dossier, gestion de version, création de soumission documentaire, import binaire, ordre/rotation/recadrage et confirmation documentaire selon les routes auditées. Les identifiants et révisions proviennent des réponses serveur. Le contrôle local d’un formulaire ne vaut pas conformité documentaire ou validation de crédit.

## Conditions restant avant utilisation réelle

Aucune URL de backend déployé ni session métier n’a été fournie. Il reste donc à :

1. Déployer et configurer authentification, cookies sécurisés, CSRF et proxy métier.
2. Brancher la lecture persistante des dossiers et la reprise des brouillons ; actuellement, les données de demande et fichiers ne survivent pas au rechargement. Un avertissement de départ protège les saisies en cours.
3. Fournir la projection serveur autorisée d’un rapport effectivement publié et son chargement pour l’analyse et l’accompagnement. `CreditServices.publishedReport` reste vide ; aucun résultat n’est fabriqué. Le rendu d’analyse existant doit être qualifié sur cette projection réelle, dont le score lorsqu’il est disponible.
4. Valider en bout en bout comptes particuliers/entreprises, séparation entre utilisateurs, dépôt/revue/conformité, rapports, permissions, expiration de session et reprise après erreur réseau.
5. Vérifier les en-têtes de sécurité réellement servis, l’accessibilité et les performances sur appareils mobiles cibles.

L’accès privé de la plateforme est conservé. Cette livraison améliore et durcit le frontend ; elle ne certifie pas encore l’exploitation de la plateforme complète avec des dossiers réels.

## Ajustements de navigation — 4 novembre 2026

Les sept rubriques sont disponibles dans le bouton Menu. Profil et Paramètres quittent la barre supérieure. Le menu indique la rubrique active, se ferme au choix d’un lien, au clic extérieur et avec Échap ; les flèches, Début et Fin permettent de parcourir ses liens au clavier.

En saisie, le grand titre, les textes d’introduction et la barre générale des étapes sont masqués pour laisser place aux onglets du formulaire. Ces onglets sont horizontaux, centrés sur l’étape active et disposent d’un espace aux extrémités pour centrer aussi le premier et le dernier onglet. Les cases à cocher et boutons radio ont leurs styles propres, avec états sélectionné, non sélectionné, survol, désactivé et focus clavier.

Contrôles navigateur : accès au Profil par le menu, fermeture avec Échap et retour du focus, affichage du menu mobile, états des cases. Écart de centrage mesuré au dernier onglet : 0,125 px sur ordinateur et −0,414 px en largeur mobile ; aucun débordement horizontal global à 375 px utiles. Les 62 contrôles frontend existants passent après les modifications.
