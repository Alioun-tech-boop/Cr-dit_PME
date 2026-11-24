# Éditions PDF professionnelles — composition LaTeX

Les PDF officiels sont composés avec pdfLaTeX à partir du contrat Presentation figé de
l'édition. Le moteur de rendu n'accède ni au dossier métier ni aux moteurs financiers :
il ne recalcule aucun ratio, score, seuil ou recommandation.

## Identité visuelle

- Couverture dédiée avec titre, statut, marque et métadonnées du dossier.
- Sommaire et sections hiérarchisées.
- Typographie Latin Modern, encodage T1 et prise en charge du français.
- Palette Crédix bleu nuit / turquoise, tableaux à lignes alternées et en-têtes répétés.
- En-têtes et pieds de page, pagination totale, marges A4 et liens de vérification.
- Conservation des textes longs, des accents et des valeurs inconnues.

## Installation

L'image Docker installe texlive-latex-base, texlive-latex-recommended,
texlive-latex-extra, texlive-lang-french et lmodern. Sur Debian/Ubuntu, l'installation
locale équivalente est :

```bash
sudo apt-get update
sudo apt-get install -y texlive-latex-base texlive-latex-recommended \
  texlive-latex-extra texlive-lang-french lmodern
pdflatex --version
```

Aucun téléchargement de paquet TeX n'est effectué à l'exécution.

La compilation est exécutée dans le worker isolé, sans shell escape, avec durée,
mémoire, taille de sortie et nombre de pages bornés. Le rendu HTML d'aperçu reste
disponible séparément ; la sortie PDF téléchargée est celle composée en LaTeX.

## Historique et validation

Les PDF déjà émis restent immuables et ne sont pas régénérés. Les nouvelles éditions
utilisent le nouveau moteur. La suite de tests doit être exécutée dans l'image qui
contient TeX Live ; une validation visuelle des PDF produits est également requise
avant la mise en production.
