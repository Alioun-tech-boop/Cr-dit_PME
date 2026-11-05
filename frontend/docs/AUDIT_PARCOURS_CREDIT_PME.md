# Crédit PME — audit du projet et correspondance du parcours frontend

Date : 4 novembre 2026. Référence backend examinée : `Alioun-tech-boop/Cr-dit_PME`, commit `a22b7ab43b5836bf4796798b2bd013ab5959055e`.

## Conclusion

Le backend existe réellement et dépasse largement l’ancienne démonstration frontend. Il réunit deux noyaux financiers, un parcours documentaire avec politiques, préparation des pages, OCR et revue, des analyses détaillées, des suggestions, des simulations, des instantanés historiques et des éditions imprimables. Le défaut principal du frontend initial était l’absence du parcours métier et de raccordement à ces contrats.

La nouvelle version ajoute les pages et les interactions nécessaires pour explorer le parcours. Elle reste une démonstration exécutée dans le navigateur : aucun dossier ni document n’est envoyé au backend, aucun OCR n’est exécuté en ligne et aucun résultat personnalisé n’est fabriqué. Les pages d’analyse et d’accompagnement exploitent les rapports réellement générés par les moteurs Python sur deux exemples synthétiques du dépôt.

Aucune adresse de service backend distant, session métier de production ou configuration d’accès interorigines n’a été fournie ou trouvée dans les éléments examinés. Le README décrit un service local. L’existence du code ne démontre pas que ce service est actuellement déployé et accessible depuis le site.

## 1. Périmètre réellement examiné

Lecture des sources des modules `credit/individuals`, `credit/businesses`, `credit/shared`, `credit/assessment`, `credit/documents`, `credit/printing`, `credit/security`, de l’API, de la persistance, des migrations et des tests disponibles au commit de référence. Lecture des guides d’analyse, scans, impressions, permissions et audit de sécurité. Lecture des contrats Pydantic, politiques documentaires et grilles illustratives. Consultation des quatre dossiers financiers de base et de deux scénarios détaillés.

L’inspection porte sur une copie des fichiers récupérés depuis GitHub. Elle n’a pas modifié le dépôt backend, ses identités, ses secrets ni sa base. Les tests HTTP, PostgreSQL, OCR français, ClamAV et restauration n’ont pas été réexécutés dans cet environnement. Les nombres de tests mentionnés dans les rapports antérieurs restent des résultats documentés par le dépôt, distincts des vérifications exécutées ici.

## 2. Ce qui est effectivement implémenté au backend

| Domaine | Présence constatée dans les sources | Conséquence pour le frontend |
|---|---|---|
| Particuliers | Salarié, retraité, indépendant ; ménage, revenus nets, charges essentielles, retenues, dettes, réserve | Parcours adapté au profil, budget personnel distinct de l’activité professionnelle |
| Entreprises | Comptabilité structurée ou flux reconstitués ; encaissements, dépenses, impôts, investissements, prélèvements, dette | Distinction des flux directs, du résultat comptable et du BFR |
| Contrats | Pydantic, champs inattendus refusés, montants exacts en Decimal | Les valeurs inconnues restent nulles ; ne jamais les convertir en zéro |
| Pièces | 132 profils, politiques `scan_required`, `original_preferred`, `structured_required` | Choix du type, du rôle et de la période ; les formulaires structurés précèdent les justificatifs |
| Préparation | Originaux séparés des dérivés, pages stables, ordre, rotation, recadrage et révisions | Aperçu et préparation sans écraser l’original |
| OCR | Extraction et français, traitement borné, attente explicite si dépendance manquante | Montrer l’état réel, pas seulement le code HTTP |
| Revue | Corrections tracées, période et montant validés séparément, rattachement explicite à une cible | Un candidat OCR ne devient jamais automatiquement un montant utilisable |
| Analyse | 7 sections particulier, 9 sections entreprise ; indicateurs, règles, sources, alertes et lacunes | Écran détaillé et explicable, distinct d’une simple jauge |
| Risque | Déficits et tensions de trésorerie, hypothèses, grille versionnée éventuelle | Séparer qualité documentaire, capacité financière et décision |
| Modèle | Fournisseur absent : `not_available` | Pas de score 70/30 ni de probabilité inventée |
| Suggestions | Priorités, déclencheurs, destinataires, prérequis, justificatifs et limites | Plan d’action explicite ; aucune promesse d’accord |
| Simulations | Stress, montant inférieur, durée, calendrier, restructuration, retard de démarrage | Une nouvelle simulation conserve le scénario de référence |
| Impression | Catalogue de modèles, HTML/PDF, versions demandeur/analyste, autorisation de communication | Séparer impression locale et édition serveur autorisée |
| Persistance | SQLAlchemy, Alembic, instantanés, historique, empreintes, version de dossier | Une modification ne doit pas réécrire une analyse passée |
| Sécurité | Jetons, institution et droits par dossier, rôles, contrôle des objets, quotas et audit | Une bascule visuelle ne confère aucun rôle réel |

### Noyau particulier : sept sections réelles

1. Identité, ménage et qualité documentaire.
2. Revenus et stabilité.
3. Dépenses essentielles et budget du ménage.
4. Dettes et comportement de remboursement.
5. Capacité de remboursement.
6. Réserve et résistance aux difficultés.
7. Cohérence du financement.

Le disponible est calculé à partir des revenus personnels nets, des charges essentielles et des échéances. Le traitement des retenues salariales doit être explicite pour éviter leur double déduction. Les revenus professionnels d’un indépendant ne se confondent pas avec son revenu personnel mobilisable.

### Noyau entreprise : neuf sections réelles

1. Identité juridique et qualité documentaire.
2. Activité et modèle économique.
3. Rentabilité.
4. Cycle d’exploitation et BFR.
5. Trésorerie.
6. Endettement et structure financière.
7. Capacité de remboursement.
8. Projet financé et résistance aux chocs.
9. Garanties et recouvrement.

Le BFR n’est pas retranché une seconde fois des flux directs. Les nouveaux financements et les emplois financés sont séparés des encaissements d’exploitation. Une garantie ne corrige pas une marge déficitaire. Un bénéfice comptable ne prouve pas la disponibilité de liquidités à chaque échéance.

## 3. Contraintes qui déterminent l’ordre des pages

### Saisie avant documents

Les routes de création de dossier attendent un contrat financier complet. Il n’existe pas, au commit examiné, de ressource publique de brouillon partiel accompagnée d’une API de sauvegarde étape par étape. Le frontend peut collecter les réponses progressivement ; la création métier doit attendre un document valide, ou une API dédiée aux brouillons doit être ajoutée.

### Conformité à plusieurs niveaux

Les états de dépôt, qualité, OCR, revue et authenticité sont distincts. Une pièce présente et lisible peut encore contenir une contradiction. Une transcription revue ne certifie pas une signature ni l’authenticité. Le backend conserve expressément `authenticity_status=not_assessed` ; le frontend ne doit jamais le transformer en « document certifié ».

Une conformité documentaire suffisante ne garantit pas un résultat favorable de solvabilité. L’analyse peut aussi rester partielle et retourner des informations manquantes. La page de résultats doit les conserver visibles.

### Autorisations avant résultats

Le demandeur n’est pas autorisé à lire les analyses brutes ou à exécuter l’OCR et les revues. Le serveur réserve ces opérations aux rôles internes habilités, puis propose une restitution imprimable filtrée et une autorisation de communication liée à une analyse donnée. Les résultats du portail demandeur doivent respecter cette projection, pas appeler indistinctement l’endpoint interne `/assessments/{id}`.

## 4. Correspondance des nouvelles pages

| Page | Nouveau comportement | Base du backend |
|---|---|---|
| Choix du crédit | Particulier ou entreprise, profil, objet du projet ; redirection vers le premier formulaire | `profile`, `mode`, `analysis_details.funding` |
| Identité | Nom, coordonnées, ménage ou entreprise/représentant | `RecordDetails`, `household_scope`, `activity` |
| Projet | Usage, capital, besoin, apport annoncé et taux facultatif | `FundingPlan`, `Loan` |
| Revenus/flux | Périodes explicites observées/prévisionnelles, inconnus séparés de zéro | `IndividualPeriod`, `BusinessPeriod` |
| Échéances | Nouveau crédit et échéances existantes, références et horizon | `Payment`, `Loan` |
| Compléments | Réserve/historique ou comptabilité/BFR/garanties | `IndividualDetails`, `BusinessDetails` |
| Hypothèses | Explications de prévision et commentaires | `projection_assumptions`, `project_assumptions` |
| Documents | Import local PDF/JPEG/PNG, capture mobile, aperçu, ordre, rotation et cadrage des images | `NewSubmission`, `PageEdit`, politiques |
| Vérification | Cohérence locale, pièces présentes, états explicites, revue serveur encore attendue | Contrats, droits et cycle de dépôt |
| Analyse | Synthèse immersive, tableaux par période, 7/9 sections, détails et hypothèses | `AssessmentReport` |
| Accompagnement | Actions classées, déclencheurs, destinataires, prérequis, limites, progression personnelle | `Suggestion` |

Les catégories de crédit visibles sont des objets de projet, pas un catalogue d’offres bancaires validées. Elles doivent être remplacées ou rapprochées des produits approuvés de chaque institution avant calcul d’un score par politique.

Les familles documentaires internes de politique et vérification ne sont pas proposées au demandeur. Les références du catalogue sont conservées ; le fait d’embarquer une copie ne lui confère pas l’autorité du serveur.

## 5. Réalisation frontend et limites actuelles

### Fonctionnel dans cette livraison

- Navigation entre les étapes, formulaires conditionnels et reprise de brouillons dans la même page.
- Tableaux de périodes, échéances et dettes ; contrôles de cohérence locaux.
- Montants sérialisés sous forme de chaînes ; somme du capital rapprochée en centimes entiers.
- Import local, contrôle sommaire de signature/poids, dimensions d’images, aperçu, préparation des images.
- Séparation visible des contrôles non effectués : OCR, qualité serveur, revue et authenticité.
- Export d’un dossier complet ou d’un brouillon explicitement identifié comme tel.
- Deux exemples synthétiques du dépôt, analysés par le moteur Python ; scénarios de base et baisse de 20 %.
- Détails de sections, traçabilité, constats, suggestions, suivi personnel des actions et impression navigateur.
- Cartes arrondies, noir pur, contours affirmés, photos réelles et adaptations pour mobile.

### Non réalisé en ligne

Aucune sauvegarde distante, authentification métier, création de dossier en base, transmission des originaux, segmentation des PDF en pages, OCR, traitement d’arrière-plan, revue d’analyste, publication de résultats personnalisés ni génération de PDF serveur n’est déclenché par ce site. Le cadrage d’image est une préparation locale, pas une preuve de contrôle de qualité. La pagination des PDF doit être inspectée par le serveur. Les données et fichiers sélectionnés disparaissent au rechargement.

L’adaptateur `credit-api.js` formalise les routes et en-têtes constatés, mais n’est pas branché à l’application. Il n’installe ni session ni délégation de droits. Aucun jeton n’est embarqué. L’existence de cet adaptateur ne constitue pas une intégration terminée.

Les formulaires couvrent les entrées principales, pas encore tous les tableaux avancés du backend : contreparties multiples, ventilation fine des charges, flux intramensuels datés, observations de remboursement détaillées, historiques comptables multiples, garanties multiples et rattachements de preuves validées. Ces entrées nécessitent des vues dédiées et une validation métier avant exploitation réelle. Les exemples du dépôt conservent leurs données avancées intactes.

## 6. Raccordement nécessaire, dans un ordre concret

1. Définir l’URL de service cible et son mode d’hébergement. Le service local du README n’est pas accessible automatiquement depuis le site.
2. Mettre en place une identité de production et une passerelle de même origine ou une politique CORS étroite, sans ouvrir les analyses internes au demandeur. Ne pas placer de jeton d’analyste dans le frontend.
3. Ajouter une API de brouillons partiels et une liste paginée des dossiers autorisés, absentes des routes métier examinées. Le frontend ne doit pas inventer une persistance depuis un simple message de succès.
4. Créer le dossier financier lorsque les contrats sont satisfaits. Conserver l’ID et la version renvoyés ; utiliser `If-Match` lors des remplacements. Une version périmée doit inviter à recharger, jamais écraser silencieusement.
5. Charger les politiques documentaires autorisées côté serveur. La route actuelle `/documents/policies` traverse les contrôles internes ; prévoir une projection publique adaptée au demandeur si nécessaire.
6. Créer chaque dépôt avec type, rôle et période, envoyer les binaires, préparer les pages avec leur révision, puis confirmer. L’API attend le binaire, pas un formulaire multipart inventé.
7. Afficher et suivre les états réels. Dépendance OCR manquante, saturation, délai, annulation et conflit doivent rester distincts. Pas de « succès » fondé sur le seul HTTP 200 de `/process`.
8. Proposer un espace analyste pour la revue : original, résultat OCR, zone source, correction, période, devise et unité. Rattacher ensuite explicitement le montant au bon champ.
9. Exécuter l’analyse avec une clé d’idempotence liée à l’opération, puis conserver l’instantané et sa version. Respecter les règles de politique réelle ou de démonstration.
10. Publier uniquement les résultats sélectionnés pour le demandeur, selon les habilitations et l’autorisation de communication du backend. Une projection JSON de résultats publiés serait utile si l’on veut une page interactive plutôt qu’une édition HTML/PDF.
11. Relier les suggestions aux pièces et aux simulations réellement disponibles, avec leurs hypothèses et leurs coûts. Une case « action traitée » n’est pas une validation de l’analyste.
12. Relier le catalogue d’éditions et les téléchargements autorisés ; ne pas assimiler l’impression navigateur à un PDF serveur archivé.

### Erreurs à gérer explicitement

401 : identité requise ou expirée ; 403 : habilitation absente ; 404 : ressource non accessible ; 409 : état, révision ou clé incompatible ; 413 : quota de fichier ; 422 : contrat, format ou politique non respecté ; 428 : version de dossier requise ; 429 : capacité occupée ; 503 : dépendance ou service indisponible. Éviter les relances aveugles des créations non idempotentes.

## 7. Vérifications réellement exécutées pendant cette livraison

**24 contrôles JavaScript** : exactitude des centimes au-delà de la précision des nombres flottants, valeurs inconnues et zéro, invariants de capital/périodes, conservation des exemples, exports déclaratifs, en-têtes de version et d’idempotence de l’adaptateur, absence de jeton par défaut et refus d’un endpoint HTTP externe.

**20 contrôles Python** (interpréteur disponible, Pydantic 2.14.1 ; ce n’est pas la réinstallation de l’environnement verrouillé du backend) : validation des deux exports de formulaires par les vrais contrats Pydantic ; absence de contrôles d’identité forgés ; calcul sans grille/modèle ; refus de capital incohérent ; résultats financiers de référence ; 7/9 sections ; absence de mutation des entrées ; stress défavorable ; égalité des rapports et scénarios affichés avec les sorties des moteurs.

Valeurs de référence observées : particulier, première marge **70 000 FCFA** ; entreprise saisonnière, première marge **−213 000 FCFA**, première trésorerie finale **−203 000 FCFA**. Ces chiffres appartiennent aux exemples synthétiques, pas à un utilisateur.

Vérifications dans le navigateur : redirection du choix vers le premier formulaire, enchaînement des six formulaires entreprise, étape documents, vérification et confirmations, ouverture des neuf sections d’analyse et accès aux suggestions. Le rendu mobile à 390 px a été inspecté. Un scan PNG synthétique a été importé, prévisualisé et recadré ; le parcours a ensuite conservé l’état de revue serveur en attente. La capture réelle par appareil photo dépend du téléphone et n’a pas été testée dans ce navigateur distant.

Les rapports de sécurité du dépôt mentionnent **234 tests backend** sur SQLite et PostgreSQL et **167 tests du module PDF**. Ils n’ont pas été réexécutés ici : aucun résultat de cette livraison ne doit être présenté comme leur répétition.

## 8. Ce qui reste ouvert au niveau du projet entier

Pas de modèle entraîné, de PD calibrée ou de grille réelle approuvée fournis. La combinaison 70/30 n’est autorisée que si deux scores compatibles et validés existent. Pas de décision de prêt automatique.

Le dépôt documente des protections locales et des corrections importantes, mais conserve des sujets de production ouverts : SSO/MFA, TLS effectivement déployé, chiffrement et gestion des secrets, antivirus opérationnel avec signatures, isolation renforcée, conservation et suppression, exploitation et sauvegardes gérées. Cet audit de correspondance frontend ne les clôt pas.

Le résultat de cette livraison est un parcours frontend cohérent et vérifiable à partir du backend, accompagné d’une liste précise des raccordements manquants. Il ne faut pas utiliser cette démonstration pour traiter des dossiers réels.
