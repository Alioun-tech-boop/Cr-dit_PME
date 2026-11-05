# Repères du financement sur l’accueil

L’anneau segmenté sert à présenter l’analyse de crédit de Crédit PME. Le visuel de
référence inspire le rendu ; il ne définit ni les intitulés ni la logique métier.
Les données proviennent du résultat autorisé du noyau concerné, en FCFA.

## Particuliers

Titre : **Emprunter. Préserver votre équilibre.**

- **Capacité** : marge après charges essentielles et échéances de crédit. Le
  graphique distingue échéances existantes, nouveau crédit et marge positive
  restante. Les ressources disponibles avant dette et les échéances à couvrir
  restent affichées pour comprendre le calcul, même en cas d’insuffisance.
- **Échéances** : capital, intérêts et frais exigibles pendant la période. Il ne
  s’agit pas du capital restant dû.
- **Réserve** : réserve projetée après les flux, comparée au solde mobilisable
  initial. L’épargne bloquée n’est pas incluse.

## Entreprises / PME

Titre : **Financer l’activité. Préserver sa trésorerie.**

- **Capacité** : marge de remboursement après les sorties nécessaires de l’activité.
- **Dette** : service des dettes existantes et du financement demandé.
- **Trésorerie** : solde projeté après exploitation, dette, financements et emploi
  des fonds. Une variation positive n’est pas présentée comme du bénéfice.

Les vues de liquidité distinguent solde initial et variation cumulée positive,
ou solde restant et réduction. Si le solde devient négatif, le montant reste
négatif au centre ; les parts positives distinguent le solde initial absorbé et
le manque supplémentaire projeté. Les pourcentages sont uniquement ceux des
catégories représentées, jamais des probabilités de défaut ou un score de risque.

## Fiabilité et droits

`report.budget_chart`, conservé comme nom de champ pour compatibilité, utilise
le schéma `credit-pme.credit-overview.v2`. Il est restitué par la route existante
`GET /api/{core}/{case_id}/published-assessment` après contrôle des droits.

La projection utilise l’instantané de l’analyse et les résultats des noyaux, jamais
le dossier modifié depuis. Le demandeur doit bénéficier d’une publication des
résultats financiers : une publication limitée aux suggestions ne suffit pas.
Le navigateur ne recalcule aucun montant métier. Les dettes déjà déduites, le BFR,
les financements et leur emploi restent traités par les noyaux existants.

Les valeurs inconnues restent indisponibles. Zéro reste zéro. Les prévisions sont
identifiées. Les montants sont décimaux (HALF_UP, deux décimales, chaînes JSON),
les parts négatives ne sont pas dessinées et les insuffisances restent signalées.
La déconnexion retire les données de la page. Aucun accord de crédit automatique.

## Vérifications

Les contrôles couvrent la marge de référence de 70 000 FCFA, les échéances de
130 000 FCFA et la réserve projetée de 1 070 000 FCFA du dossier synthétique utilisé
par le navigateur. Ces données de test ne sont pas préchargées dans le site.
Les 21 contrôles Chromium couvrent les onglets adaptés, les périodes réelles,
le clavier, le mobile, les déficits PME et la déconnexion. Captures desktop et mobile
réellement générées et inspectées sous `output/frontend/browser-*/`, exclu de Git.
Les tests Python vérifient aussi les liquidités en hausse, baisse, déficit, nulles
ou inconnues, les décimaux exacts, la publication et l’isolation des accès.

```bash
uv run pytest tests/test_budget_chart.py tests/test_web_integration.py -q
(cd frontend && npm test)
uv run python -m scripts.run_frontend_e2e --browser-test budget-widget.cjs
```

Aucune migration, connexion bancaire ou dépendance graphique supplémentaire.

Dernière validation : 257 tests backend réussis (2 avertissements de dépréciation),
23 tests ciblés de projection et d’accès réussis, 21 contrôles Chromium réussis.
