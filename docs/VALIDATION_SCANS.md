# Vérifications exécutées — parcours de dépôt v0.2

Date : 4 novembre 2026. Hôte Debian 13.6, Python 3.12.14, PostgreSQL 16.6,
Tesseract 5.5.0 et modèle français disponibles. Les dépendances du backend restent
verrouillées dans `uv.lock` ; Pillow, déjà installé avec le module, est désormais
une dépendance directe du parcours. Aucun document réel n'a été utilisé.

## Résultats observés

| Vérification exécutée | Résultat |
|---|---|
| `.venv/bin/python -m pytest -q` | **77 tests réussis**, 42,36 s |
| Même commande avec `TEST_DATABASE_URL=…/credit_test` | **77 tests réussis**, 50,79 s |
| Depuis `modules/credit_pme_pdf`, `../../.venv/bin/python -m unittest discover -s tests -v` avec le modèle local configuré | **167 tests réussis**, aucun ignoré, 7,415 s |
| `ruff check .` | Réussi |
| `ruff format --check .` | 43 fichiers déjà formatés ; module fourni exclu du reformatage |
| `uv pip check` | 38 paquets compatibles |
| Construction de l'image Docker avec certificat du proxy monté en secret | Réussie |
| Migration locale réelle | `0003 (head)` ; anciennes tables et données conservées |
| `tesseract --list-langs` dans le conteneur | `eng`, `fra`, `osd` |
| Démonstrateur HTTP sur backend Python puis Docker | Dépôts JPEG/PNG/PDF dans les deux noyaux, ordre/rotation/recadrage, OCR fra et revue réussis |
| Redémarrage de PostgreSQL et de l'API, puis `demo_scans.py --verify-existing` | JSON des dépôts, dossiers, runs, revues et événements identiques ; empreintes des 3 sources identiques |
| Appel sans jeton à la politique documentaire sur HTTP réel | 401 ; `/health` reste disponible |
| Démonstrateur financier existant avec identité | Quatre dossiers synthétiques analysés, scénarios exécutés |
| Comparaison des fichiers fournis à l'archive | **162 fichiers strictement identiques**, module non modifié |

Les commandes et leurs prérequis sont dans [PARCOURS_SCANS.md](PARCOURS_SCANS.md).
Les journaux de test sont dans `output/pdf/`, et les réponses, sources référencées
et images de comparaison du démonstrateur dans `output/scans/api/`. Ces dossiers
sont exclus du suivi Git et des images Docker.

Le test de redémarrage compare l'état complet sauvegardé par le démonstrateur à
celui relu via HTTP, ainsi que les SHA-256 des originaux téléchargés. Il ne se limite
pas à vérifier que `/health` répond. La migration réelle a conservé les dossiers
créés avant elle ; leur accès nécessite maintenant une attribution explicite s'ils
n'avaient pas de propriétaire.

## Couverture de l'acceptation

Les tests du projet couvrent notamment :

- JPEG et PNG décodables, MIME et extension trompeurs, fichier corrompu.
- Format admis configuré par type documentaire, limites de taille annoncée et lue,
  pixels, cumul des sources, nombre de pages et délai de réception.
- Scan sans texte, scan avec couche OCR, PDF natif refusé sous `scan_required`,
  petit logo insuffisant, PDF natif accepté sous `original_preferred` avec tableaux
  natifs conservés, page mixte et PDF multipage avec page vide supprimable.
- Exception native justifiée et habilitée, politiques liées aux 132 profils,
  collecte structurée obligatoire et justificatif qui ne remplit pas un champ inconnu.
- Ordre et suppression des pages, y compris suppression de la dernière page,
  rotation, recadrage et contrôle de révision concurrente.
- Transformations géométriques : les coordonnées d'un mot natif transformé puis
  ramené à sa source correspondent à l'original pour 0/90/180/270 degrés et recadrage.
  Les coordonnées EXIF sont également contrôlées.
- Doublon exact, flou synthétique, contraste/exposition, contenu près des bords,
  orientation mesurée ou explicitement indéterminée, blocage d'une page vide/uniforme.
- Dépendance française absente simulée, source conservée et reprise avec vrai OCR
  français ; échec OCR explicite ; processus réellement arrêté sur expiration ;
  saturation du pool refusée. Le test anglais du module d'origine reste distinct.
- Original récupéré sans modification après édition ; résultat brut inchangé après
  correction ; agent et date provenant du serveur ; zone source manuelle pour une
  donnée absente ; habilitation de revue requise.
- Accès refusé aux dossiers, analyses, images, originaux, résultats et revues d'un
  autre agent ; droits explicites aux anciens dossiers ; configuration d'identités
  manquante ou invalide refusée ; modes fichier et JSON d'identités.
- Séparation Particuliers/Entreprises, identifiants croisés refusés, absence de
  changement du dossier financier ou de son résultat après dépôt et revue.

Les 35 tests financiers/API initiaux sont conservés, avec adaptation des clients
à l'identité requise. Les anciens tests d'envoi PDF direct ont été adaptés à la
lecture historique et au refus 410 ; le nouveau parcours porte la couverture des
dépôts, erreurs, droits et sources. Aucun contournement natif n'est laissé ouvert
pour garder artificiellement le comportement de l'ancien POST.

## Contrôles métier réellement observés

Le scan synthétique a produit un candidat de salaire net `280000 XOF`, avec page,
rectangle, identifiant de source, empreinte et matrice inverse. Le relevé natif a
conservé son tableau et le crédit `280 000`. La revue humaine a conservé la valeur
brute, ajouté une transcription justifiée et laissé `authenticity_status=not_assessed`
et `ready_for_scoring=false`.

Le démonstrateur appelle explicitement le calcul financier avant et après le dépôt
pour prouver son absence de modification. Le dépôt, la confirmation, le traitement
et la revue n'appellent eux-mêmes aucun calcul financier, score ou modèle d'entraînement.

## Corrections apportées pendant la validation

- Persistance des états finaux : nouvelle copie du dictionnaire JSON après le commit
  de l'état `running`, pour éviter une mutation interne non suivie par SQLAlchemy.
- Paramètres d'admission : limites du dépôt transmises au worker et formats contrôlés
  sur le contenu décodé, au lieu de servir uniquement de métadonnées.
- Pages vides : prévisualisation possible mais confirmation bloquée.
- Sources géométriques : correspondance testée sur les mots réellement transformés,
  sans supposer que des libellés volontairement tournés restent reconnus comme champs.
- Collecte structurée : clés nécessaires déclarées dans le référentiel ; `null`
  reste explicite et n'est pas remplacé par une valeur issue du justificatif.
- Temporaire OCR : `TMPDIR` du worker sous le dossier privé du parent, pour nettoyer
  aussi les images de Tesseract après une expiration et l'arrêt du groupe de processus.

## Limites restant à lever

Aucun blocage d'installation, de langue française ou de service local ne reste
constaté. Un avertissement Starlette TestClient / AnyIO `BlockingPortal` demeure,
sans test en échec. Les tests de charge, sécurité adversariale, authentification de
production et restauration de sauvegarde n'ont pas été exécutés.

L'identité locale n'est pas un annuaire de production. Le contrôle de couverture
image ne prouve pas une origine papier et ne détecte pas toute coupure ou tout
doublon visuel. Les seuils qualité sont des paramètres techniques à calibrer sur
un corpus autorisé et annoté, pas une norme validée au Burkina Faso. Aucune mesure
de précision sur pièces réelles ni vérification de signature/authenticité n'est revendiquée.

Pas de frontend dans le dépôt : livraison API, prévisualisations autorisées et
exemples d'usage. Le traitement synchrone en processus borné n'est pas une queue
distribuée ni un sandbox de sécurité OS. Stockage privé existant en base, sans
chiffrement applicatif ni politique automatisée de purge. Les dossiers anciens
nécessitent un droit explicite ; les nouveaux appartiennent à l'agent créateur.

## Fichiers ajoutés ou modifiés

- `credit/auth.py`, `credit/api.py` : identité locale, droits par dossier, protection
  des analyses, schéma Bearer Swagger et branchement du parcours.
- `credit/persistence.py`, `migrations/versions/0003_scan_workflow.py` : propriétaire,
  dépôts, sources, runs, événements, revues et collectes structurées.
- `credit/documents/intake_contracts.py`, `intake_routes.py`, `intake_service.py` :
  contrats et orchestration du parcours ; `routes.py` : lecture historique et POST 410.
- `credit/documents/policy.py`, `policies.v1.json`, `quality.v1.json` : référentiels
  et paramètres techniques versionnés.
- `credit/documents/imaging.py`, `geometry.py`, `isolation.py`, `worker.py` : décodage,
  qualité, géométrie, provenance et processus bornés.
- `pyproject.toml`, `uv.lock`, `compose.yaml`, `.env.example` : dépendances et configuration.
- `examples/scans/` : générateur et huit pièces/images entièrement synthétiques.
- `scripts/init_local_auth.py`, `demo_scans.py`, `demo.py`, `demo_pdf_api.py` : initialisation,
  démonstration et compatibilité CLI avec le nouveau parcours.
- `tests/conftest.py`, `test_api.py`, `test_documents.py`, `test_scan_workflow.py` :
  identités de test, régression et acceptation.
- `README.md`, `docs/EXTRACTION_PDF.md`, `docs/PARCOURS_SCANS.md`,
  `docs/VALIDATION_SCANS.md`, `VALIDATION.md` : guides et rapports.

Les identités privées dans `.local/auth/` et résultats dans `output/` ne sont pas
livrés comme sources à suivre dans Git. Aucun fichier du module fourni n'a été modifié.
