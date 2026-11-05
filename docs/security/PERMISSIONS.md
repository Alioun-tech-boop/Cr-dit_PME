# Matrice d’autorisations

Identité, rôle et institution proviennent exclusivement du registre serveur.
Chaque accès métier vérifie institution **et** propriétaire ou droit explicite sur
le dossier. Un responsable ou administrateur n’a pas de contournement automatique
vers une autre institution ni vers tous les dossiers. Registres historiques :
`reviewer=true` correspond à analyste ; sinon demandeur. Une configuration de rôle
explicite prévaut sur ces anciens indicateurs.

| Opération | Demandeur | Analyste | Responsable institution | Administrateur |
|---|---|---|---|---|
| Créer un dossier réel | Oui | Oui | Oui | Oui |
| Créer un dossier synthétique | Non | Local seulement | Local seulement | Local seulement |
| Lire/modifier un dossier autorisé | Champs publics, version requise pour modifier | Oui | Oui | Oui |
| Institution, rôle, score, décision par JSON | Non | Non | Non | Non |
| Forger statut vérifié / revue serveur | Non | Non | Non | Non |
| Observations internes | Non | Oui | Oui | Oui |
| Pièce et pages publiques du dossier | Oui | Oui | Oui | Oui |
| Pièce marquée interne, sources et versions | Non | Oui | Oui | Oui |
| Gérer pages / confirmer un dépôt autorisé | Oui | Oui | Oui | Oui |
| OCR et annulation autorisés | Non | Oui | Oui | Oui |
| Revoir une transcription courante | Non | Oui | Oui | Oui |
| Calcul brut, analyse, simulation, historique interne | Non | Oui | Oui | Oui |
| Générer/lire une édition demandeur | Oui | Oui | Oui | Oui |
| Générer/lire une édition analyste | Non | Oui | Oui | Oui |
| Autoriser communication de résultats sélectionnés | Non | Oui | Oui | Oui |
| Audit institutionnel structuré | Non | Non | Institution seulement | Institution seulement |
| Modifier registre/politiques sur disque | Aucun endpoint HTTP ; opérateur OS autorisé et procédure de changement |

Les pièces transmises par un agent pour le demandeur sont publiques par défaut dans
le périmètre de ce dossier ; utiliser `visibility=analyst` pour une pièce interne.
Les anciens dépôts sans champ de visibilité sont fermés au demandeur, sauf s’il en
est l’auteur. Les anciennes extractions PDF directes exigent une habilitation interne.
La liste des pièces d’un PDF demandeur filtre aussi les pièces internes.

La génération d’un PDF n’est jamais son partage externe. Les autorisations de
communication sont attachées à l’analyse précise. Les mêmes contrôles s’appliquent
aux anciens PDF, originaux, images dérivées, runs, revues, tâches et éditions.
Une route administrative avec un compte ordinaire renvoie 403 ; un objet hors
périmètre renvoie 404. Aucune institution fournie dans un JSON ne peut définir
le contexte d’accès. Les politiques sont chargées depuis un registre serveur,
pas des artefacts de modèle fournis par le client.

## Passerelle navigateur (5 novembre 2026)

Les sessions HttpOnly utilisent la même identité serveur ; elles n’élargissent
aucun droit de la matrice. Seul un opérateur serveur provisionne le mot de passe
Argon2id. Aucun rôle ni institution ne peut être choisi à la connexion.
Les brouillons UI incomplets restent privés à leur propriétaire et à leur
institution, y compris face à un autre analyste. Le rattachement à un dossier
existant vérifie ses droits avant toute écriture. Les versions restent requises.
Une lecture demandeur de l’analyse utilise une projection explicitement publiée,
excluant sections internes, règles, scores et sources, avant sérialisation.
Voir [contrats, limites et configuration](../FRONTEND_BACKEND.md).
