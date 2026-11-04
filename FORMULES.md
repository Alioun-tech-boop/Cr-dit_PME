# Formules et hypothèses — moteur deterministic-0.1.0

Le calcul porte sur les périodes explicitement fournies, triées et uniques. Une date
est la clé d'un intervalle choisi par l'analyste (exemples : mois calendaires,
identifiés par leur premier jour). Tous les flux d'une même clé doivent couvrir le
même intervalle. Aucun montant annuel n'est converti implicitement en montant mensuel.
Les échéances explicites sont affectées à ces clés par égalité de date : agréger les
échéances du mois sur sa clé avant import si nécessaire. L'horizon doit couvrir
l'intégralité des échéanciers soumis. Le capital renseigné est le capital restant
à rembourser de ces échéanciers ; il doit être égal à leur somme de principal.

## Particuliers

- Disponible avant dettes = revenus personnels nets retenus − dépenses essentielles.
- Marge = disponible − capital, intérêts et frais des dettes existantes et demandée.
- Réserve fin = réserve début + marge. Le capital du prêt demandé n'est pas un revenu
  personnel : cette réserve mesure la capacité de paiement hors fonds affectés du prêt.
- Poids des échéances = service total / revenus, uniquement si revenus > 0.
- Si le salaire reçu est après retenues de prêts, ces retenues sont réintégrées au
  revenu avant déduction des échéanciers. Une retenue supérieure aux échéances
  existantes recensées exige un rapprochement. Un traitement non identifié rend la
  période incomplète. Les références de dette doivent être uniques.
- Indépendant : revenu personnel après coûts professionnels nécessaires. Les
  composantes optionnelles encaissements/coûts sont soustraites et rapprochées du net.
  Sinon l'entrée doit confirmer un net déjà calculé après coûts, avec références de
  preuve. Un chiffre d'affaires seul ne constitue jamais un revenu personnel retenu.
- Variabilité = écart type de population / moyenne, sur au moins trois observations
  historiques antérieures aux projections, de moyenne positive. Elle ne décrit pas
  une probabilité de remboursement et n'est pas calculée sur les projections.

## Entreprises

- Sorties nécessaires = exploitation + impôts + investissements indispensables
  hors emplois du financement + prélèvements du ménage non inclus dans l'exploitation.
- Disponible pour dette = encaissements d'exploitation − sorties nécessaires.
- Marge = disponible − services de dette existante et nouvelle (capital/intérêts/frais).
- Trésorerie fin = début + marge + décaissements du crédit demandé − emplois financés.
- Couverture du service de dette = disponible / service total, si service > 0.
- Trésorerie minimale = minimum des soldes de fin de période, avec première date
  correspondante. Si un solde est inconnu, le minimum global reste inconnu.
- Les emplois financés doivent être exclus des investissements indispensables et des
  charges déjà recensées. Un décaissement reçu sans emploi conserve réellement les
  fonds en caisse ; aucun emploi fictif n'est supposé. Leur somme doit correspondre
  au principal demandé lorsque ces montants sont connus.
- Les créances, fournisseurs et stocks sont documentaires ; aucune variation du BFR
  n'est soustraite une seconde fois des flux directs. Comptabilité structurée et
  flux reconstitués fournissent les mêmes agrégats de trésorerie, avec provenance distincte.
- Les historiques de flux sont conservés séparément des projections. Aucun résultat
  comptable, indicateur de concentration ou de rentabilité n'est inventé à partir
  d'agrégats de trésorerie qui ne permettent pas de le calculer.

## États des données, stress et arrondis

`known/0` signifie zéro observé ; `unknown/null` signifie inconnu ;
`not_applicable/null` signifie non applicable ; `estimated/valeur` est une estimation.
Un montant critique inconnu ou non applicable rend l'analyse incomplète. Les intérêts,
frais et autres postes optionnels explicitement non applicables ne contribuent pas
au total. Les valeurs inconnues se propagent jusqu'aux soldes suivants sans devenir zéro.
Les preuves contradictoires ou manquantes empêchent de retenir les montants liés.
Les montants sans référence de preuve sont signalés séparément dans la qualité
documentaire ; une analyse financière complète n'implique pas des preuves vérifiées.

Montants en `Decimal`, XOF uniquement, au plus 24 chiffres et deux décimales.
Les exemples utilisent des francs entiers ; les centimes sont une précision technique
pour les échéanciers, sans prétention à définir les règles contractuelles locales.
Entrées sans arrondi implicite ; valeurs calculées sous stress et intérêts arrondis
au centième `ROUND_HALF_UP`. Sérialisation JSON des décimaux en chaînes, ratios sans
arrondi monétaire. Aucune conversion de devises implicite.

Stress : revenus/encaissements × (1 − baisse), dépenses essentielles des particuliers
ou exploitation des entreprises × (1 + hausse). Impôts, dette, investissements,
prélèvements et emplois financés restent ceux fournis. Le montant retardé est déplacé
après application de la baisse ; il ne peut dépasser l'encaissement restant. Départ
et arrivée doivent être dans l'horizon. Les hypothèses sont conservées ; aucune valeur
illustrative ne constitue une norme. Comparer une analyse de base et une analyse de
scénario du même dossier pour mesurer l'effet.

Générateur : taux nominal annuel exprimé en fraction (`0.12` = 12 %), taux mensuel =
taux annuel / 12, échéance hors frais = `P*r/(1-(1+r)^(-n))`, ou `P/n` si taux nul.
Intérêts calculés sur le capital restant, principal égal à échéance hors frais moins
intérêts, plafonné au restant. Dernier principal ajusté exactement au solde afin que la
somme du capital remboursé égale le capital. Frais par échéance séparés. Jour conservé
ou ramené au dernier jour du mois si nécessaire. Ce calcul n'est pas un taux effectif
réglementaire.

## Scores et décision

Chaque noyau expose une interface de critères et de prédiction. Politique versionnée
`70-30-v1` : 0,70 critères + 0,30 modèle uniquement si deux scores utilisables sont sur
la même échelle validée. Aucune grille ni aucun modèle ne sont fournis ou activés :
critères indisponibles, `model_status=not_available`, score combiné `null`.
Constats financiers, sortie de score, recommandation et décision du prêteur sont
séparés. Les deux derniers restent `null`. Un score sur 100 n'est pas une probabilité.
