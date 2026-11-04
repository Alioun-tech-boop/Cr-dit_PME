# Résultats d’exécution

Les résultats définitifs sont reportés après exécution des commandes, sans
extrapolation à partir d’un test non exécuté. Référence avant correction :
**181 tests backend réussis**, **167 tests module PDF réussis**.

Les reproductions locales avant/après sont enregistrées dans :

- `output/security/reproductions-before.json`
- `output/security/reproductions-after.json`
- `output/security/baseline-project.log` et `baseline-module.log`
- `output/security/project-after.log`, `postgres-after.log`, `module-after.log`
- `output/security/dependencies-before.json`, `dependencies-after.json`
- `output/security/backup/result.json` et `backup-restore.log`
- `output/security/secret-scan.json`

Ces sorties locales sont ignorées par Git ; elles ne contiennent que des cas
synthétiques, des empreintes et des journaux techniques. Le dump de test est privé.
Le registre livré `findings.json` donne gravité, preuve, conséquence, correction,
test et statut final pour chaque constat.


## Résultats finaux obtenus

- Backend sur SQLite : **234 tests réussis**, dont 53 nouveaux tests d’audit.
- Même suite sur PostgreSQL dédié : **234 tests réussis**.
- Module PDF, depuis son dossier, après mise à jour de PyMuPDF : **167 tests réussis**.
- Ruff : aucune erreur ; 83 fichiers conformes au format ; `git diff --check` sans erreur.
- `uv lock --check --offline` : résolution verrouillée cohérente (44 paquets).
- `pip-audit` : neuf avis connus / trois paquets avant ; **aucun avis connu** dans
  l’inventaire interrogé après mise à jour. Portée et applicabilité dans `AUDIT.md`.
- Recherche ciblée de secrets : aucune correspondance dans les fichiers non ignorés
  du projet. Ce contrôle ne prouve pas l’absence de tout secret possible.
- Sauvegarde/restauration : résultat `passed`, empreintes du PDF et du scan identiques,
  instantané et audit restaurés sur deux bases synthétiques créées et supprimées par
  le script ; refus des privilèges SQL interdits vérifiés avec un rôle temporaire.
- Création, rotation et révocation de jetons essayées uniquement sur registres
  temporaires synthétiques ; rôle, institution, expiration et mode privé vérifiés.
- Reproductions : fuite interne supprimée, analyse brute demandeur refusée 403,
  mise à jour sans version refusée 428, marges des deux routes identiques à 60 000
  avec charge supplémentaire, résultat indépendant du contexte Decimal appelant.

## Vérifications dans le service Docker local

Image reconstruite avec certificat du proxy et dépendances verrouillées. Migration
`0006 (head)` appliquée. API et PostgreSQL sains sur leurs ports de boucle locale.
Contrôle des sources de l’image contre le dépôt (SHA256) réussi sur les composants
critiques. API UID **10001**, racine **read-only**, capacités **ALL retirées**,
`CapEff=0` et `NoNewPrivs=1` effectivement observés.

Le parcours HTTP a généré 17 éditions imprimables depuis quatre dossiers. Le parcours
de scans a traversé les deux noyaux avec JPEG/PNG/PDF, géométrie, OCR français,
revue et sources, sans alimentation automatique du scoring. Après redémarrage API,
les PDF, métadonnées, dépôts, sources, extractions et revues ont été retrouvés à
l’identique. Aucun service externe n’a reçu de dossier ou de rapport.

Deux avertissements de dépréciation d’outils de test subsistent, sans échec.
Les éléments de production non exécutés (TLS réel, MFA/SSO, antivirus avec signatures,
chiffrement, isolation FS forte et politique de rétention) restent explicitement
ouverts ; aucune préparation à la production ou certification n’en est déduite.

## Réexécuter les contrôles de dépendances

```bash
mkdir -p output/security
uv export --locked --no-hashes --no-emit-project --no-emit-package credit-pme-pdf \
  --format requirements-txt > output/security/requirements-audit.txt
uvx --from pip-audit==2.9.0 pip-audit --disable-pip --no-deps \
  -r output/security/requirements-audit.txt --format json \
  --output output/security/dependencies-recheck.json
```

Le module local n’a pas d’avis PyPI interrogeable ; ses dépendances restent dans
l’inventaire. Les signatures des paquets de l’installation sont dans `uv.lock`.
Ce contrôle réseau de versions ne constitue pas un audit complet de leur code.
