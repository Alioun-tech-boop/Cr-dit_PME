# Référence des calculs audités

Montants : XOF, `Decimal`, arrondi monétaire au centième `ROUND_HALF_UP`. Cette
convention technique ne prétend pas être une convention bancaire réglementaire
validée pour l’émission de paiements FCFA. Utiliser des chaînes décimales ou des
entiers exacts en JSON ; les nombres flottants monétaires sont refusés, y compris
lors du rattachement d’une transcription contrôlée.

## Particuliers

```text
revenus_nets_retenus = somme des revenus personnels nets mobilisables déclarés
                      + retenues de prêts déjà déduites, si leur traitement est identifié
disponible_avant_dettes = revenus_nets_retenus − dépenses_essentielles
marge_après_crédit = disponible_avant_dettes − échéances_existantes − nouvelles_échéances
réserve_fin = réserve_début + marge_après_crédit
poids_des_échéances = (échéances_existantes + nouvelles_échéances) / revenus_nets_retenus
```

Ratio indisponible si revenus non positifs ou inconnus. Une réserve n’est pas un
revenu permanent. Les retenues ambiguës empêchent un calcul certain. Les charges
supplémentaires explicitement hors total sont intégrées une seule fois, sur copie,
par les deux routes d’analyse. L’indépendant doit justifier un revenu personnel net
après coûts professionnels ; le chiffre d’affaires n’est pas un revenu disponible.

Cas témoin : 500 000 − 300 000 − 50 000 − 80 000 = **70 000** ; sous baisse des revenus
à 400 000, la marge devient **−30 000**, sans modifier les dépenses ni échéances.

## Entreprises / PME

```text
disponible_pour_dette = encaissements − sorties_nécessaires_hors_dette
service_total = capital + intérêts + frais exigibles, dettes existantes et demandée
marge_après_dette = disponible_pour_dette − service_total
trésorerie_fin = trésorerie_début + marge_après_dette
                + financement_reçu − emplois_du_financement
couverture = disponible_pour_dette / service_total, si service_total > 0
```

Les sorties nécessaires couvrent exploitation, impôts, investissements indispensables
et prélèvements du ménage hors charges déjà incluses. Les financements ne sont pas
des revenus d’exploitation. Une variation de BFR n’est pas déduite une seconde fois
avec les flux directs. Aucun compte de résultat n’est déduit de simples encaissements.
Les ratios comptables exigent unité et période comparables, dénominateur valide et
données nécessaires ; fonds propres nuls/négatifs sont traités explicitement.

Cas témoin : 4 000 000 − 3 000 000 = 1 000 000 ; service 250 000 + 400 000 = 650 000 ;
marge **350 000** ; couverture **20/13**. Une rupture mensuelle reste signalée même
si la somme annuelle est favorable. Une garantie n’efface pas cette insuffisance.

## Échéanciers, stress et valeurs manquantes

Le générateur mensuel utilise `r = taux_nominal_annuel / 12`, paiement hors frais
`P × r / (1 − (1+r)^(-n))`, ou `P/n` au taux nul. Les intérêts et le capital sont
arrondis selon la convention ; la dernière échéance rembourse le solde restant.
Les frais restent séparés. Le capital total remboursé est vérifié. Aucun taux
effectif réglementaire n’est calculé. Les échéanciers irréguliers sont des références
explicites, sans conversion implicite en mensualités constantes.

Les limites techniques (montants, taux nominal ≤10 en fraction, hausse de dépenses
≤10, taille des dossiers) préviennent les abus ; elles ne sont ni seuils d’accord,
ni taux d’usure ou normes de crédit. Les contraintes de produit restent distinctes.

Les stress portent sur les données explicites : revenus nets retenus pour les
particuliers, encaissements pour les entreprises ; hausse des dépenses essentielles
pour les particuliers et d’exploitation pour les entreprises. Impôts, échéances et
investissements ne sont pas arbitrairement redimensionnés. Les retards déplacent
un montant entre périodes existantes. Si l’encaissement source est inconnu,
l’encaissement reporté est aussi inconnu. Aucune moyenne n’est prolongée pour
combler une durée supplémentaire : projections et hypothèses explicites requises.

Un inconnu ne devient pas zéro ; une dette au capital et à l’échéancier inconnus
ne donne pas un service certain de zéro. Les « non applicable » optionnels sont
traités selon le contrat et restent identifiables dans les sources. Les données
OCR non revues ne sont pas automatiquement consommées.

## Scores et reproductibilité

Score de solvabilité : 0–100, élevé favorable. Indice de risque : 100 − score,
**sans interprétation de probabilité**. Poids fixes contrôlés, sans renormalisation
si données/sections nécessaires manquent. Politique illustrative : démonstration
synthétique seulement, interdite en production. Revue obligatoire sur les déficits.

Combinaison future : `0,70 × critères + 0,30 × modèle` seulement si les deux scores
sont disponibles, compatibles et autorisés. Aucun modèle entraîné n’est fourni.
La PD et la perte attendue nécessitent leurs propres justifications, horizon et
périmètre ; aucun calcul `1 − score/100` n’est utilisé comme PD.

Les fonctions de calcul fixent leur contexte Decimal indépendamment de celui du
thread appelant. Instantanés, preuves, versions des moteurs/règles et hypothèses
restent conservés. Les simulations utilisent des copies ; un rapport émis ne
recalcule pas les scores et ne change pas après modification du dossier.
