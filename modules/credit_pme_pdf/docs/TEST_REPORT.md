# Rapport de vérification — 4 novembre 2026

## Résultats exécutés

- `python -m unittest discover -s tests -v` : **167 tests réussis**, aucun échec,
  aucune erreur, aucun test ignoré ; durée de la dernière exécution : 7,700 s.
- 132 tests de profils : création de PDF synthétiques avec les premiers alias de
  tous les champs de chaque profil, extraction et conservation des candidats.
- 35 autres tests : montants et provenance, classification prudente, dossiers
  composites, données manquantes, valeurs contradictoires, séparateurs ambigus,
  décimaux/négatifs/zéro, dates, unités, tableaux, colonnes N/N-1, AcroForm,
  PDF invalides/chiffrés, limites taille/pages, OCR manquant, langue manquante,
  OCR réel anglais, options invalides, empreintes, revue humaine, CLI, lots,
  API HTTP avec authentification et refus d'une interface non locale.
- Traitement CLI du manifeste complet : **132 pièces traitées sur 132**, sorties
  séparées, aucun échec.
- 137 PDF synthétiques générés ; revue visuelle du bulletin détaillé et du bilan
  à deux exercices : aucun chevauchement ni troncature constaté.
- 5 sorties détaillées livrées dans `examples/results` : bulletin natif, bulletin
  scanné lu par OCR anglais, relevé avec tableau, bilan à deux exercices, formulaire.

## Environnement observé

- Python 3.12.14.
- PyMuPDF 1.26.6.
- pdfplumber 0.11.9.
- ReportLab 4.4.9 pour les fixtures.
- Tesseract présent, modèles `eng` et `osd` disponibles.
- Modèle français `fra` **absent** : le chemin d'erreur de langue manquante est
  testé ; l'OCR français n'a pas pu être exécuté ici.
- Aucun paquet téléchargé, aucun document client réel, aucun appel IA externe.
- Pas de conteneur : Docker n'est pas présent dans cet environnement.

## Portée des preuves

Ces tests démontrent le fonctionnement du module sur les cas synthétiques
décrits. Ils ne mesurent pas la précision sur des CNIB, bilans, relevés ou scans
réels de banques et IMF. Les variantes de mise en page, tous les alias secondaires,
les tableaux sans bordures, les manuscrits et les documents dégradés ne sont pas
couverts par une validation terrain. Aucun OCR ne certifie un document.

Le socle produit des candidats traçables ; aucun résultat n'est automatiquement
admis dans un score ou une base d'entraînement. Les étapes suivantes sont
l'installation d'OCR français, la constitution d'un corpus autorisé et annoté,
l'ajout de profils de mise en page et le branchement aux deux noyaux métier.
