# Branchement aux deux noyaux

1. Le backend attribue le dossier, son propriétaire, son type particulier ou
   entreprise, la pièce attendue et la période d'analyse.
2. Il transmet les octets PDF au module, avec un type explicite issu du catalogue
   lorsqu'il le connaît. Il conserve l'original dans un espace privé.
3. Il conserve le résultat brut avec son empreinte et sa version. La lecture OCR
   et les tableaux restent des preuves non vérifiées.
4. Un agent contrôle le rattachement au bon client, les dates, la devise, l'échelle,
   les colonnes et les montants. Les corrections sont tracées sans écraser la source.
5. Un adaptateur métier distinct sélectionne les valeurs validées et applique les
   contraintes de chaque noyau. Il ne doit pas prendre le premier candidat.
6. Le noyau Particuliers distingue revenus avant/après retenues de prêts et dettes
   existantes pour éviter le double comptage. Le noyau Entreprises sépare les
   encaissements d'exploitation, transferts et nouveaux financements.
7. Le suivi des décisions et remboursements reste séparé. Les tableaux d'historique
   extraits ne deviennent des exemples d'entraînement qu'après rapprochement,
   validation des identifiants, de la chronologie et de la définition de défaut.

## Contrôles à implémenter dans le backend hôte

- Droits d'accès au dossier et à l'original, par utilisateur et institution.
- Préservation des versions et source de toute donnée.
- Validation des champs critiques selon le profil et le produit de crédit.
- Contrôle des unités, monnaies et périodes avant calcul.
- Rapprochement des multiples comptes et neutralisation des transferts internes.
- Journal de décision avec utilisateur authentifié, distinct du nom d'agent de la CLI.
- Politique de conservation, suppression et protection des données.

Ces contrôles ne sont pas remplacés par le champ `review_status` de ce module.
`ready_for_scoring` reste toujours faux : le backend est responsable d'un contrat
d'entrée métier validé, propre au noyau concerné.
