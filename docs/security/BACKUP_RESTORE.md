# Sauvegarde, restauration et conservation

Les données métier et fichiers privés (originaux, dérivés, PDF émis) résident dans
PostgreSQL. Le registre d’identités est séparé dans un fichier privé ; les politiques
et versions du moteur font partie du code. Une sauvegarde utilisable doit couvrir
ces trois périmètres, avec accès et gestion des secrets séparés.

## Essai exécuté sans données réelles

```bash
.venv/bin/python scripts/verify_backup_restore.py
```

Ce script exige le Compose PostgreSQL local et ses identifiants de démonstration.
Il crée deux bases aux noms aléatoires `audit_source_*` / `audit_restore_*`, applique
les migrations à la première, puis crée un dossier synthétique, une analyse, un scan original et un
PDF. Il effectue `pg_dump --format=custom`, restaure dans la seconde et compare
le dossier, l’empreinte d’entrée d’analyse, les octets du PDF et du scan original,
ainsi que le nombre d’événements d’audit. Il vérifie aussi les
droits du rôle SQL runtime : lecture autorisée, création de table et modification
historique interdites, suppression de l’audit et lecture de `pg_authid` refusées.

Seuls les objets dont la création a réussi dans ce script sont supprimés au
nettoyage. Aucune base préexistante ni donnée réelle n’est supprimée. Le dump
synthétique et le résultat sont dans `output/security/backup/`, permissions privées,
hors Git. Le script n’est pas une commande de sauvegarde de production.

## Procédure opérateur pour une vraie sauvegarde

1. Identifier la base, sa version PostgreSQL et le compte de sauvegarde autorisé.
   Fournir les secrets par le gestionnaire de secrets ou `PGPASSFILE` privé, jamais
   en argument de commande, dans le dépôt ou dans un journal.
2. Choisir un répertoire privé et appliquer `umask 077`. Utiliser TLS avec vérification
   du serveur pour un accès réseau. Les noms ci-dessous sont des chemins opérateur,
   jamais des paramètres d’une route utilisateur.
3. Effectuer la sauvegarde sans supprimer de données :

```bash
umask 077
pg_dump --dbname="$BACKUP_DATABASE_URL" --format=custom --no-owner --no-acl \
  --file="$BACKUP_DIRECTORY/credit-pme.dump"
sha256sum "$BACKUP_DIRECTORY/credit-pme.dump" > "$BACKUP_DIRECTORY/credit-pme.dump.sha256"
pg_restore --list "$BACKUP_DIRECTORY/credit-pme.dump" > "$BACKUP_DIRECTORY/manifest.txt"
```

Le DSN doit exclure le mot de passe si les commandes du système sont visibles à
d’autres utilisateurs ; utiliser `PGPASSFILE`/service libpq. Les dumps contiennent
les informations sensibles et les fichiers. Chiffrer le support via une infrastructure
appropriée, avec clés gérées séparément. Aucun chiffrement artisanal n’est ajouté.

4. Sauvegarder séparément le registre d’identités, les politiques approuvées, le
   commit/image déployé et la version Alembic. Conserver les permissions privées.
   Ne pas fusionner secrets et sauvegarde financière dans un espace public.
5. Restaurer uniquement dans une **nouvelle base isolée** :

```bash
createdb --maintenance-db="$RESTORE_ADMIN_URL" credit_restore_check
pg_restore --dbname="$RESTORE_CHECK_URL" --no-owner --no-acl --exit-on-error \
  "$BACKUP_DIRECTORY/credit-pme.dump"
```

Ne pas utiliser `--clean` contre la base active. Désactiver tout partage externe,
traitement asynchrone ou action bancaire sur la copie de restauration. Vérifier
les tables, migrations, clés étrangères, cas et analyses témoins, sources et
empreintes des PDF. Les secrets et droits doivent être réappliqués explicitement.
La remise en service d’une base réelle nécessite l’autorisation du responsable.

## Privilèges runtime et déploiement

Après migrations effectuées avec un rôle séparé, un DBA peut appliquer :

```bash
psql "$MIGRATION_DATABASE_URL" -v app_role=credit_runtime -f ops/runtime_grants.sql
```

Le rôle LOGIN doit être créé séparément, avec secret géré, sans superuser,
createdb, createrole ou bypassrls. Le compte applicatif ne migre pas la production.
Les droits fournis sont testés sur une copie synthétique ; aucune modification de
rôle de production n’a été faite. La séparation institutionnelle reste applicative,
sans politique RLS ajoutée dans cet audit.

## Conservation et intégrité

Aucune purge réelle ou automatique n’est activée. Définir avec l’institution les
durées applicables aux dossiers, preuves, versions, journaux, sauvegardes et
éventuels litiges. Tester une rétention uniquement sur des copies synthétiques,
avec autorisation explicite avant suppression réelle. Le compte runtime ne reçoit
pas de droit DELETE général sur les historiques.

L’audit en base n’est pas inviolable face à un administrateur ; prévoir un collecteur
externe et des sauvegardes protégées. Aucun engagement RPO/RTO, chiffrement au repos
ou restauration de production n’est annoncé comme vérifié dans cet environnement.
