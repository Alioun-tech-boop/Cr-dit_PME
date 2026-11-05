# Vidéos réelles de l’accueil

Deux séquences filmées réelles, et non générées, remplacent les photos des deux
cartes de l’accueil. Les autres pages et leurs photos restent inchangées.

| Fichier local | Source et auteur | Sujet |
|---|---|---|
| `dist/assets/videos/card-payment.mp4` | [Pexels 6683942 — Kampus Production](https://www.pexels.com/video/a-man-paying-with-credit-card-6683942/) | Paiement par carte auprès d’un commerçant |
| `dist/assets/videos/banking-atm.mp4` | [Pexels 6276983 — Uriel Mont](https://www.pexels.com/video/woman-using-a-atm-machine-6276983/) | Utilisation d’un distributeur bancaire |

Sources téléchargées le 5 novembre 2026 sous la [licence Pexels](https://www.pexels.com/license/),
autorisant leur intégration dans un site commercial et leur adaptation. Les personnes
filmées ne sont pas présentées comme clientes ou partenaires de Crédit PME.
Les fichiers sont intégrés à la présentation du site ; ne pas les redistribuer
comme une banque de vidéos indépendante. Aucune affiliation bancaire n’est suggérée.

Extraits de 8 secondes, sans piste audio, MP4 H.264/yuv420p avec métadonnées de
lecture au début du fichier (`faststart`). Les affiches sont des images extraites
des séquences elles-mêmes. Les crédits sont aussi présents dans le pied de page.

Les vidéos sont servies depuis la même origine que le site : aucun lecteur tiers,
aucun suivi publicitaire et aucune extension de la CSP n’est nécessaire.
Elles sont chargées à l’entrée de la carte dans le viewport, mises en pause hors
écran et lorsque l’onglet est masqué. Les préférences de mouvement et le mode
économie de données empêchent la lecture automatique ; le bouton Lire permet un
choix explicite. Le bouton Pause reste disponible au clavier. Une lecture bloquée
ou une vidéo indisponible laisse l’affiche visible.

## Vérifications exécutées

- `npm test` : 30 contrôles de contrats, 40 contrôles de livraison/transport et
  3 contrôles de frontières asynchrones réussis ; syntaxe des 10 scripts vérifiée.
- `npm run test:home-videos` : 15 contrôles réels dans Chromium, sur la passerelle
  ASGI locale (`CREDIT_PREVIEW_URL=http://127.0.0.1:8010` pour cette vérification).
  Décodage, progression des images, pause, clavier, mobile, préférences et
  erreur réseau vérifiés ; aucune erreur JavaScript ni requête média externe.
- `ffprobe` : 8 secondes chacun, H.264, aucune piste audio ; 527 609 et 504 528 octets.
- Captures desktop et mobile réellement produites et inspectées dans
  `output/home-videos/`, exclu du suivi Git.

Pour relancer les contrôles sur le service local habituel :

```bash
cd frontend
npm test
CREDIT_PREVIEW_URL=http://127.0.0.1:8000 npm run test:home-videos
```
