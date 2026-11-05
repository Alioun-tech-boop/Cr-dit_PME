# Analyse financière déterministe v2

Les [résultats des vérifications exécutées](VALIDATION_FINANCIAL_V2.md) distinguent tests, rendu et limites.

Le nouveau parcours `financial_analysis_v2` remplace la fusion prédictive pour les
nouvelles analyses de l’interface. Les routes historiques `/assessments` restent
compatibles ; leurs instantanés, rapports et PDF émis ne sont ni migrés ni recalculés.
Le stockage JSON versionné `AssessmentRecord` existant suffit : aucune modification
SQL ni migration destructive n’est nécessaire.

## Exécution locale — Linux, Python 3.12

Depuis la racine, après le provisionnement des comptes expliqué dans
[FRONTEND_BACKEND.md](FRONTEND_BACKEND.md) :

```bash
uv sync --locked
cd frontend && npm ci && npm run build && cd ..
docker compose up -d db
export DATABASE_URL=postgresql+psycopg://credit:credit_local@127.0.0.1:5432/credit
export CREDIT_AUTH_FILE="$PWD/.local/auth/users.json"
export CREDIT_WEB_ORIGIN=http://127.0.0.1:8000
export TESSDATA_PREFIX="$PWD/.local/share/tessdata"
.venv/bin/alembic upgrade head
.venv/bin/uvicorn credit.web.application:app --host 127.0.0.1 --port 8000 --no-access-log
```

Ouvrir exactement `http://127.0.0.1:8000`. Les sessions métier, le cookie HttpOnly,
le CSRF et la passerelle de même origine restent obligatoires. Aucun jeton de service
n’est inclus dans le navigateur. Aucun compte ni mot de passe par défaut n’est ajouté.

```bash
.venv/bin/pytest -q
cd frontend && npm test && cd ..
.venv/bin/python -m scripts.run_frontend_e2e
.venv/bin/python -m examples.financial_v2.generate
.venv/bin/python -m scripts.validate_financial_v2_pdfs
```

Les dossiers et rapports synthétiques sont dans `examples/financial_v2/` : particulier
de contrôle, dossier incomplet, entreprise rentable sous tension et activité saisonnière.
La génération d’exemples n’appelle ni API, ni base, ni fournisseur d’IA.

## API et interface

- `POST /{individuals|businesses}/{case_id}/financial-analyses` : `AnalysisRequest`.
- `GET /financial-analyses/{id}` et `/report` : JSON et texte français.
- `POST /financial-analyses/{id}/simulations` : objet `Stress`, nouvelle analyse liée
  à son parent, hypothèses et comparaison avant/après enregistrées.
- `POST /financial-analyses/{id}/exceptions` : `limit_ids` et `reason` (10 caractères
  minimum), responsable d’institution ou administrateur autorisé au dossier seulement.
  L’auteur, l’institution, la date, les limites et le motif sont conservés dans une
  édition enfant. Les calculs, scores et qualifications ne sont pas réécrits.
- Historique et lecture compatibles : `/{core}/{id}/assessments`, `/assessments/{id}`.
- HTML/PDF existants : `/{core}/{id}/print/preview`, `/print/editions`, puis
  `/print-editions/{edition_id}/pdf`. La requête contient l’`assessment_id` v2.

Les opérations v2 exigent un rôle analyste habilité et les droits sur l’objet et son
institution. Les règles de publication demandeur restent inchangées : les détails
internes, sources et scores ne sont pas transmis sans autorisation prévue. Le PDF
analyste détaillé ajoute rapprochements, scénarios, seuils et variantes ; son modèle
est `print-financial-v2.0.0`. Le modèle de présentation ne recalcule aucun score.

Dans l’interface, « Lancer l’analyse réelle » utilise v2. « Paramètres de l’analyse
approfondie » enregistre la configuration JSON dans le brouillon persistant ; le
serveur la valide à l’exécution. Le résultat approfondi utilise des panneaux dépliables
et les composants existants. Aucune zone active « IA 30 % » dans ce parcours ; les
anciennes analyses conservent leur restitution historique. Le paramétrage avancé
reste destiné à un analyste technique ; ce n’est pas encore un éditeur visuel de barèmes.

Exemple de corps (montants décimaux sous forme de chaînes) :

```json
{
  "policy_id": null,
  "mode": "real",
  "validated_sources": [],
  "facts": {},
  "scenarios": [{"id":"revenu-20", "name":"Baisse hypothétique de 20 %",
    "revenue_drop":"0.20", "rationale":"Hypothèse explicitement choisie par l’analyste"}],
  "reverse_tests": [{"parameter":"revenue_drop", "lower":"0", "upper":"0.50"}],
  "financing_candidates": []
}
```

Pour un client API autorisé (le jeton personnel reste dans l’environnement du terminal) :

```bash
curl --fail-with-body -H "Authorization: Bearer $CREDIT_TOKEN" \
  -H 'Content-Type: application/json' -H 'If-Match: 1' \
  -H 'Idempotency-Key: analyse-v2-personnelle-001' \
  --data @examples/financial_v2/individual_control.request.json \
  "http://127.0.0.1:8000/api/individuals/$CASE_ID/financial-analyses"
```

Cet exemple particulier utilise une politique **illustrative** : le dossier doit
être synthétique, son produit `unclassified`, `CREDIT_ALLOW_DEMO=true`, et le serveur
ne doit pas être en production. Pour des faits réels, utiliser `mode=real` et une
politique approuvée ou `policy_id=null` (calculs et constats sans score).
`If-Match` vérifie la version lorsqu’il est fourni ; le frontend le fournit.
`Idempotency-Key` réutilise la même analyse à données et requête identiques et répond
409 si ces données ont changé. Une simulation accepte aussi cette clé.

## Calculs et chaîne de preuve

Deux moteurs indépendants orchestrent validation, normalisation, rapprochement,
reconstitution, indicateurs, historique, projection, stress, règles, sous-analyses,
variantes et rapport. Le noyau pur fonctionne sans HTTP ni base.

Particulier :

- disponible avant dette = revenus nets retenus − dépenses essentielles ;
- marge = disponible avant dette − échéances existantes − nouvelles échéances ;
- réserve de fin = réserve de début + marge, sans assimiler la réserve à un revenu ;
- poids des échéances = service total / revenus strictement positifs.

La retenue de prêt déjà déduite du salaire est réintégrée avant de soustraire le
service de dette une seule fois. Une retenue ambiguë bloque le calcul concerné.
Le revenu indépendant reste net des coûts professionnels ; un scénario de baisse
porte sur ce revenu personnel, pas sur un chiffre d’affaires assimilé à un salaire.
Aucune dépense essentielle absente n’est estimée automatiquement.

Entreprise :

- disponible pour dette = encaissements − sorties nécessaires hors dette ;
- marge = disponible pour dette − capital, intérêts et frais des deux services ;
- trésorerie fin = trésorerie début + marge + emprunt reçu − emploi des fonds ;
- couverture = disponible pour dette / service total strictement positif.

Les transferts internes restent exclus par le contrat existant (aucun import brut
de transactions n’est ajouté). Le BFR de bilan est informatif, jamais redéduit des
flux directs. Une bonne rentabilité ne neutralise pas un mois déficitaire.
Les garanties restent une section distincte et ne modifient pas la capacité calculée.

Montants : `Decimal`, XOF/FCFA, arrondi au centième `ROUND_HALF_UP`. Calculs en précision
28 ; ratios de sections à huit décimales. Aucun change implicite ; une devise autre
que XOF est refusée. Les bilans complémentaires exigent `unit_multiplier` égal à
`1`, `1000` ou `1000000`. Les valeurs nulles, inconnues et non applicables restent
distinctes. Les sources non contrôlées issues de l’OCR ne deviennent pas des entrées
validées ; `validated_sources` réutilise la revue serveur, sa révision et sa période.

Le rapprochement teste `solde final = solde initial + entrées − sorties` pour le seul
compte fourni. Écarts, chevauchements, doublons potentiels et trous mensuels sont
signalés sans accusation de fraude. La couverture compte les montants utilisables,
contrôlés et inconnus ; ce n’est pas un pourcentage de confiance prédictive.

## Historique, scénarios et recherches inverses

Les moyennes, médianes, extrema, périodes à revenu nul, variation comparable et
coefficient de variation sont descriptifs. Par défaut : trois mois consécutifs
comparables au minimum. Profil saisonnier descriptif : au moins 24 mois, deux
observations de chaque mois, sans trous. Paramètres modifiables dans la politique.
Aucune moyenne ni saisonnalité n’est prolongée automatiquement dans le futur.

Le moteur couvre l’échéancier fourni et exige les mois explicites. Les données
mensuelles ne permettent pas de conclure sur toutes les tensions intramensuelles ;
les flux datés existants permettent une lecture plus fine lorsqu’ils sont complets.

Les stress modifient une copie et enregistrent ses entrées. Baisse des revenus ou
encaissements, hausse des charges essentielles (particulier) ou d’exploitation
(entreprise), perte d’une source identifiée, retard d’encaissement et retard de
recettes du projet sont disponibles. Les impôts et investissements ne baissent pas
silencieusement avec les ventes. La hausse des coûts variables nécessite une
ventilation complète rapprochée des charges ; les coûts fixes restent fixes.
Un retard est soustrait d’une période et ajouté une seule fois à une autre ; s’il
sort de l’horizon explicite, des projections supplémentaires sont demandées.
Les concentrations client après déplacement agrégé sont à rapprocher à nouveau.

Le choc de taux est limité à une réamortisation mensuelle à taux nominal connu,
frais constants et référence de clause contrôlée. Il ne représente pas tous les
contrats à taux variable, dates de refixation, indices ou plafonds ; ces conventions
nécessitent une extension dédiée. Sans preuve contrôlée, le scénario est indisponible.

La recherche inverse accepte un intervalle explicite pour baisse de revenus, hausse
de coûts, retard ou mensualité supplémentaire. Elle sonde l’intervalle avant toute
dichotomie ; une réponse non monotone utilise une exploration bornée. La monotonie
observée sur la grille n’est pas une preuve globale pour une fonction arbitraire.
Une rupture entre deux points non échantillonnés peut rester non détectée : résultat
« seuil non trouvé dans l’intervalle testé », jamais probabilité de défaut.
La mensualité supplémentaire est une enveloppe analytique avec contraintes de marge,
réserve et couverture, pas une offre de prêt générée sans taux ni capital.

## Politiques et variantes

`credit/financial_v2/policies/` fournit deux exemples `illustrative_not_validated`,
sans pondérations prétendument validées et sans scoring activé. Le répertoire peut
être configuré par `CREDIT_FINANCIAL_V2_POLICIES_DIR`. Son administration relève d’un
circuit contrôlé hors API ; le client choisit uniquement un identifiant installé.
Une approbation exige auteur, date, référence, profil, produit et éventuelle institution.
Une règle réglementaire exige en plus une référence vérifiée, son URL, sa date,
son périmètre et son vérificateur. Aucun seuil réglementaire n’est fourni.

Les opérateurs autorisés sont `ge/gt/le/lt/eq`, sans `eval`. Chaque règle trace formule,
seuil, gravité, source, version, observation et résultat. Les poids optionnels doivent
faire exactement 1 ; les phénomènes répétés et les poids sans scoring sont refusés.
Les données manquantes bloquent le score, sans renormalisation. Score élevé = plus
favorable, indice = 100 − score ; ni l’un ni l’autre n’est une PD. `model_status` vaut
`disabled_by_design`, `combined_score` et PD restent `null`.

Le simulateur explore les candidats explicitement fournis (montant, durée, apport,
calendrier, différé). Il respecte limites du produit, besoin justifié, disponibilité
de l’apport, marge, réserve, couverture et scénarios exigés. Barèmes non chevauchants,
taux et frais sont réappliqués selon montant et durée. Le différé disponible est
uniquement un différé de capital avec intérêts/frais payés, expressément configuré.
Les échéanciers irréguliers explicites restent une référence acceptée.

Chaque variante montre échéances, coût total, avant/après, hypothèses et contraintes.
Une durée dépassant les projections donne `needs_explicit_projections`. Aucun apport
annoncé n’est injecté automatiquement comme trésorerie. Le résultat maximal concerne
les seuls candidats testés, sans prétendre à un optimum global ou à un conseil.

## Références méthodologiques publiques

Consultation : **5 novembre 2026**. Ces lectures inspirent des choix de conception ;
elles ne valident ni ce moteur ni une politique de prêt et n’importent aucun fait
financier externe concernant un demandeur.

| Référence | Périmètre consulté et principe adapté | Statut / limite |
|---|---|---|
| [Commission Bancaire UMOA, circulaire 04-2017/CB/C](https://www.bceao.int/fr/documents/circulaire-ndeg04-2017cbc-relative-la-gestion-des-risques-dans-les-etablissements-de), document de 2017, mise en ligne 27/03/2018 | PDF public de 27 pages : formalisation des politiques, limites, contrôle et suivi ; adaptation : versions, approbations et revue tracée | Source publique consultée ; applicabilité juridique individuelle non certifiée ; aucun seuil réglementaire codé |
| [HSBC, Annual Report and Accounts 2025](https://www.hsbc.com/investors/results-and-announcements/annual-report), approuvé le 25/02/2026 | Rubrique « Collateral and other credit enhancements », page imprimée 132 (PDF 133) : priorité aux ressources de remboursement ; garanties complémentaires | Principe documentaire vérifié dans le PDF ; aucune reprise des modèles internes ni des paramètres de provisionnement |
| [JPMorgan Chase, Form 10-K 2025](https://www.sec.gov/Archives/edgar/data/19617/000162828026008131/jpm-20251231.htm) | Credit Risk Management et note 4, page 200 : scénarios, concentrations et revues ; adaptation : stress explicites et dépendances documentées | Source publique consultée ; pas de transposition de paramètres prudentiels ou de modèles statistiques américains |

Une pondération prudentielle d’exposition bancaire ne constitue ni le score d’un
client ni sa probabilité de défaut. Les conventions techniques Crédit PME (XOF,
arrondi, minima d’historique et exploration bornée) sont nos choix documentés, pas des
obligations BCEAO. Aucun avis d’accord, aucune certification bancaire ou réglementaire.
