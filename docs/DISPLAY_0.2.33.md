# Affichage — 0.2.33

## Problème corrigé

La vue entière restait sur un aperçu de 1 800 pixels, développé à résolution
réduite. Les régions détaillées étaient réservées au zoom et leur sélection
ignorait la densité Retina. Chaque déplacement annulait toutes les requêtes
et retirait les régions déjà affichées.

## Comportement

- Premier aperçu rapide, puis remplacement progressif par des régions issues
  du développement RAW complet, y compris en vue entière.
- Résolution choisie selon les pixels physiques de l'écran. À 100 %, un pixel
  de photo correspond à un pixel physique ; au-delà, les pixels sont agrandis.
- Conservation des détails visibles pendant le déplacement et le changement
  de niveau. Les régions communes restent en cours de chargement ; les régions
  mises en cache sont réutilisées au retour.
- Priorité au centre et aux régions visibles, puis à une marge autour de la vue.
  Deux requêtes simultanées, cache borné, rejet des réponses d'une ancienne photo
  ou recette. Les images sont décodées avant leur insertion pour éviter un flash.
- Transmission des régions détaillées en JPEG sRGB de qualité 96, sans réduction
  de résolution des canaux couleur, pour préserver les fins contours colorés.
- Comparaison sans film également détaillée, avec le même cadrage, rapport
  d'image et taille de sortie que la recette.

Le moteur photo et les paramètres d'export conservent leur fonctionnement.
Le changement de convention du zoom sur Retina est intentionnel : l'ancien
100 % agrandissait un pixel sur deux pixels physiques par côté sur un écran 2×.

## Vérifications locales

- 255 tests Python et 12 tests JavaScript réussis.
- Couverture de la vue entière et des bords, densités 1, 1,25, 2 et 3,
  correspondance du zoom, concurrence, annulation, erreurs et réutilisation.
- Contrôle du transport des contours colorés et du cadrage de la comparaison.
- Essais dans WebKit sur Retina 2× avec L1003382.DNG et L1007741.DNG :
  vue entière affinée, zooms 100 % et 200 %, déplacement, comparaison sans film,
  sélection rapide de photos et passage de PROVIA à Classic Negative.
- La vue entière de validation utilise 12 régions de niveau 4 ; le 100 % utilise
  des régions au niveau 1. Lors du déplacement testé, les 16 régions encore
  nécessaires ont été conservées. Aucune erreur de console observée.
- Application macOS construite et exécutée : aperçu, régions détaillées et
  comparaison sans film validés sur L1003382.DNG et DSCF5367.RAF. Contrôle du
  bord du RAF (région 768 × 660), du cadrage neutre et d'un rendu DNG complet
  de 9536 × 6344. Les régions détaillées conservent les trois canaux JPEG.
  Dans cette exécution, la première région incluant le développement complet
  prend 8,3 s sur le DNG et 8,2 s sur le RAF ; une nouvelle région à 100 % après
  ce développement prend respectivement 45 ms et 38 ms. Ces temps excluent
  l'ouverture initiale et ne constituent pas une garantie de délai d'affichage.

Les captures de validation et les résultats détaillés restent dans le dossier
local ignoré `outputs/display-033`. Les photos privées ne sont pas distribuées.

## Limites

Le premier aperçu reste provisoire jusqu'à « Image ready ». Le premier
développement complet peut prendre plusieurs secondes selon le RAW et le Mac.
La vue entière est échantillonnée à la résolution utile de l'écran, sans charger
une image géante de 60 mégapixels dans WebKit. Les détails à 100 % sont issus
du RAW complet ; le transport d'affichage reste du JPEG 8 bits, et non une
prévisualisation HDR ou une preuve pixel pour pixel de l'export 16 bits.
