# Crédit PME — module d'extraction PDF v0.1

Module autonome pour préparer les pièces des deux noyaux : **Particuliers** et
**Entreprises / PME**. Le code métier des noyaux de crédit n'est pas présent dans
ce dossier : le module se branche en amont, par import Python, CLI ou HTTP local.

## Périmètre complet

**132 profils de documents**, regroupés en 17 familles. Le détail des pièces,
des destinations et des champs recherchés figure dans `docs/coverage.csv` et
`docs/catalog.json`. Chaque profil possède des alias configurables en français.

Sont inclus : identité, localisation, demandes et autorisations ; documents
juridiques ; comptabilité et flux ; contrats et historiques de crédit ; pièces
commerciales ; fiscalité et cotisations ; revenus et budgets personnels ;
agriculture, élevage, transport ; garanties ; référentiels partenaires et
documents internes. Les documents internes existent dans le catalogue pour le
cas où ils sont fournis en PDF : préférer leurs originaux JSON/CSV/texte lorsqu'ils
sont disponibles.

**Couverture du catalogue ne signifie pas compréhension parfaite de chaque mise
en page.** Les champs sont des candidats obtenus par libellés explicites. Le texte
intégral, les tableaux et les champs interactifs restent accessibles pour les
contenus que les règles ne reconnaissent pas. Aucun taux de précision terrain
n'a été mesuré. Les pièces synthétiques ne constituent pas une validation bancaire.

## Ce qui fonctionne

- Lecture des PDF natifs, page par page, avec coordonnées des lignes.
- Repérage du type par titre explicite, ou choix du profil par l'appelant.
- Extraction des tableaux natifs à bordures, sans fusionner les colonnes annuelles.
- Proposition de correspondance des colonnes de transactions et échéanciers.
- Lecture des champs de formulaires PDF interactifs.
- OCR des scans et des pages mixtes, avec Tesseract local installé séparément.
- Conservation des libellés, valeurs brutes, pages, coordonnées et méthode.
- Normalisation prudente des montants, dates, taux et devises.
- Signalement des valeurs multiples, séparateurs ambigus et échelles comptables.
- Revue humaine traçable, sans écrasement des extractions initiales.
- Traitement par lot, résultat séparé par fichier, rapport d'échec par document.
- API locale, limites de taille/pages et jeton d'accès facultatif.

## Installation

Python 3.11 ou supérieur. Depuis le dossier extrait :

```bash
python -m venv .venv
# Linux / macOS :
source .venv/bin/activate
# Windows PowerShell, à la place :
# .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
```

Les versions des deux dépendances principales exécutées sont dans
`requirements-tested.txt`. Les tests utilisent également ReportLab. Aucun service
externe ni clé de fournisseur IA ne sont nécessaires.

### OCR français

Installer Tesseract **et son modèle français `fra`**, puis vérifier :

```bash
tesseract --list-langs
```

Sur Debian/Ubuntu, l'installation habituelle est :

```bash
sudo apt-get install tesseract-ocr tesseract-ocr-fra
```

Sur Windows, installer Tesseract, ajouter son dossier au PATH et installer les
données linguistiques françaises. Le code fonctionne sans chemin Windows imposé.

Le mode par défaut est `--ocr auto --lang fra`. Si `fra` manque, le résultat
signale explicitement le problème, conserve le texte natif disponible et ne
fabrique pas les données du scan. `--lang eng` est possible pour une vérification
technique ; ce n'est pas un remplacement validé du français.

## Premier essai

```bash
python -m credit_pdf catalog --output output/catalog.json
python -m credit_pdf extract examples/pdf/payslip_detail.pdf --type payslip --ocr never --output output/salaire.json
python -m credit_pdf extract examples/pdf/bank_table.pdf --type bank_statement --ocr never --output output/releve.json
python -m credit_pdf extract examples/pdf/payslip_scan.pdf --type payslip --lang fra --output output/scan.json
```

Pour un PDF chiffré, ajouter `--password-prompt`. Le mot de passe est saisi
interactivement et n'est pas inscrit dans les arguments de la commande.

Pour régénérer les exemples synthétiques :

```bash
python examples/generate_examples.py
```

Pour analyser tous les profils d'exemple :

```bash
python -m credit_pdf batch examples/manifest.json --ocr never --output-dir output/lot
```

Le manifeste décrit une liste `documents` contenant `path` et `document_type`.
Ses chemins sont relatifs au manifeste. Les sorties sont numérotées pour éviter
les collisions entre deux fichiers de même nom. Un échec n'interrompt pas les
autres pièces ; le processus sort avec le code 1 si au moins une pièce a échoué.

## Utilisation dans le backend

```python
from credit_pdf.engine import extract_pdf

result = extract_pdf(pdf_bytes, document_type="payslip", ocr="auto", lang="fra")
assert result["ready_for_scoring"] is False
candidates = result["fields"]["net_income"]["candidates"]
```

Les dossiers des particuliers et des entreprises peuvent utiliser les mêmes
documents : un relevé bancaire ne contient pas de décision sur le noyau auquel
il appartient. L'application appelante doit fournir le dossier, le propriétaire,
le rôle de la pièce et la période visée. Ne pas rapprocher des personnes sur la
seule base d'une ressemblance de noms.

## API HTTP locale

```bash
python -m credit_pdf serve --port 8765
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/catalog
curl -X POST "http://127.0.0.1:8765/extract?type=payslip&ocr=never" -H "Content-Type: application/pdf" --data-binary @examples/pdf/payslip_detail.pdf
```

Sous PowerShell, utiliser `curl.exe` si `curl` est un alias PowerShell.

Si `CREDIT_PDF_API_TOKEN` est défini dans l'environnement, ajouter
`Authorization: Bearer <jeton>` à chaque requête, y compris `/health`.
Le fichier `.env.example` est un exemple, il n'est pas chargé automatiquement.
L'API accepte directement le corps PDF binaire, pas un formulaire multipart.
Les PDF chiffrés sont gérés par la CLI ou l'import Python, pas par cet adaptateur HTTP.

Le serveur est volontairement limité à l'interface locale. Avant un déploiement
réel : intégrer à l'API du projet avec identité et droits par institution,
stockage privé, chiffrement, politique de conservation et traitement PDF/OCR
isolé en processus avec limites mémoire/CPU. Aucun contrôle de production ni
authentification d'un agent de revue n'est fourni par ce prototype.

## Contrat de sortie

- `document_sha256` : empreinte des octets d'origine.
- `pages` : texte, dimensions et candidats de type par page.
- `evidence` : lignes identifiées avec page et rectangle en points PDF.
- `tables` : cellules natives brutes, coordonnées, suggestions de colonnes.
- `form_fields` : noms, valeurs et coordonnées des champs interactifs.
- `fields` : candidats métier, jamais une valeur financière certifiée.
- `unit_hints` : mentions de devise ou d'échelle à valider.
- `warnings` : OCR, ambiguïtés, type, limites de lecture.
- `review_history` : validations/corrections humaines éventuelles.
- `ready_for_scoring` : toujours `false` dans ce module.

`not_found` signifie **libellé non détecté**, pas absence certaine de l'information.
`extracted_unverified` signifie transcription proposée, pas document authentifié.
`ambiguous_requires_review` interdit de choisir silencieusement une valeur.

Les montants sont sérialisés en chaînes décimales. `amount_as_printed` est le
nombre imprimé, sans application automatique d'une échelle « milliers » ou
« millions ». `unit_multiplier` reste inconnu. La devise d'un candidat n'est
retenue que si elle apparaît dans sa valeur ; sa propagation depuis l'en-tête
reste à valider. Ne pas additionner ces montants avant contrôle des unités.

### Revue humaine

Créer un JSON de décisions, en utilisant les identifiants de preuves réellement
présents dans le résultat :

```json
{
  "net_income": {
    "value": {"amount": "280000", "currency": "XOF", "unit_multiplier": "1"},
    "evidence_ids": ["p1:l5"],
    "reason": "Transcription contrôlée sur le document original"
  }
}
```

L'identifiant ci-dessus illustre le format : choisir l'identifiant qui correspond
à la bonne ligne dans son propre résultat.

```bash
python -m credit_pdf review output/salaire.json decisions.json --reviewer agent-demo --output output/salaire_revu.json
```

Les décisions sont ajoutées à l'historique ; les candidats bruts restent intacts.
Le nom d'agent est une attribution déclarée par la CLI, pas une identité authentifiée.
Cette opération valide une transcription, sans certifier l'authenticité de la
pièce ni remplacer les validations du noyau financier.

## Limites explicites

- Aucun LLM ni appel distant ; pas de récupération automatique de données privées.
- Les alias ne comprennent pas toutes les formulations narratives. Les annexes,
  clauses, règles partenaires et contrats sont conservés en texte ; ils ne sont
  pas convertis automatiquement en règles de crédit exécutables.
- Les tableaux natifs sans bordures, fusionnés ou irréguliers peuvent rester
  disponibles seulement dans le texte avec coordonnées.
- Les tableaux scannés sont conservés par lignes OCR ; leurs cellules ne sont
  pas reconstruites comme des données financières certifiées.
- Les manuscrits, photos inclinées et scans de mauvaise qualité peuvent nécessiter
  une saisie humaine. Les signatures, cachets, identités et titres fonciers ne
  sont pas authentifiés.
- Les champs AcroForm sont restitués séparément ; leurs noms techniques doivent
  être reliés au schéma métier du formulaire utilisé par le partenaire.
- Un PDF contenant plusieurs types de pièces ou plusieurs clients ne doit pas
  être fusionné automatiquement : segmenter et rattacher les pièces dans
  l'application appelante. Le module signale les titres multiples détectés, mais
  ne garantit pas la détection de tous les assemblages.
- Les historiques en PDF sont des pièces à rapprocher : pas de création de labels
  d'entraînement, ni d'assimilation d'un refus à un défaut. Préférer les exports
  structurés des partenaires pour les volumes importants.
- Pas de score, de modèle 70/30, d'évaluation d'authenticité ou de recommandation
  de prêt. L'intégration aux noyaux reste une étape distincte.
- Les sorties JSON contiennent les données extraites : les protéger comme les
  originaux. Les scans temporaires sont supprimés en fin d'OCR ; la mémoire
  système et les fichiers de sortie restent à gérer par l'environnement hôte.

## Vérification

```bash
python -m unittest discover -s tests -v
```

Voir `docs/TEST_REPORT.md` pour les contrôles réellement exécutés et leurs limites.
