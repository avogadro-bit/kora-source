# Affichage RAW et navigation — 0.2.37

## Changements

L'interface demande désormais un rendu à la résolution physique de l'écran,
calculé depuis le RAW entièrement décodé. Elle n'affiche plus le petit aperçu
de travail de 1 800 pixels ni le JPEG du boîtier comme premier rendu. Le rendu
écran est borné à 4 096 pixels de grand côté ; les tuiles complètent toute
résolution supplémentaire nécessaire, notamment au zoom.

Sur les machines qui autorisent le préchargement, le décodage complet débute
en même temps que l'inspection. Il n'attend plus la fin de l'estimation de
l'exposition. Un verrou par source évite de calculer deux fois cette estimation
lorsque les deux opérations la demandent ensemble. Les résultats du décodage,
la base WB et l'exposition sont identiques à ceux de 0.2.36.

Les RAW récents sont gardés en mémoire, avec un maximum de trois fichiers et
un budget de 10 % de la RAM, plafonné à 3 Gio. Un seul RAW peut dépasser ce
budget s'il est nécessaire à l'image active. Le préchargement de la photo
suivante ne peut pas évincer l'image active ; ses calculs ne bloquent pas un
zoom qui utilise déjà des pixels en cache. Les rendus d'écran possèdent un
cache séparé limité à 24 images et 64 Mio. Ces caches sont propres à la
session et ne créent pas de bibliothèque persistante de photos sur disque.

Les délais artificiels de 100 à 180 ms avant les demandes de détails sont
supprimés. Les tuiles sont réutilisées selon la photo et ses réglages, y compris
après avoir quitté puis rouvert la photo. L'image précédente reste visible
pendant un changement de recette, jusqu'à ce que son remplacement soit décodé.

Le zoom minimal est désormais **Fit**. Boutons, molette, menu et raccourcis
respectent cette limite ; le bouton moins est désactivé à la butée. Les
raccourcis +/− utilisent la même convention Retina que les autres commandes.
Le maximum reste 400 % et le 100 % conserve un pixel image par pixel physique.

## Mesures locales

Même Mac et même interpréteur de distribution, PROVIA, grain désactivé,
réduction de bruit −4, nouveau processus pour chaque campagne. La mesure
commence à l'inspection du fichier, sans cache Kora préalable ; le cache disque
du système n'est pas purgé. Avant : inspection, petit aperçu puis première
tuile détaillée. Après : inspection/décodage simultanés et rendu écran issu du
RAW complet. Ces mesures de serveur excluent le transfert et l'affichage WebKit.

| Photo | Avant : premier détail | Après : rendu écran complet | Nouvelle tuile à 100 % après chargement |
| --- | ---: | ---: | ---: |
| Leica L1007741.DNG | 12,55 s | 7,78 s | 38 ms |
| Fuji DSCF5367.RAF | 22,27 s | 14,20 s | 42 ms |

Les gains observés sont de 38 % et 36 %. Un rendu écran déjà en cache est
retrouvé côté serveur en moins de 1 ms. Cela ne mesure pas le temps complet
d'un clic dans l'interface et ne garantit pas le même délai sur tous les RAW.

## Validation et limites

- 271 tests Python et 16 tests JavaScript réussis : source complète pour le
  rendu écran, réutilisation par recette/taille, concurrence, budget mémoire,
  protection de l'image active et butée de zoom selon la densité d'écran.
- Les tableaux RAW complets Leica et Fuji ont exactement les mêmes empreintes
  SHA-256 qu'en 0.2.36 ; leurs expositions de référence sont identiques. Les
  empreintes des deux fichiers originaux restent inchangées.
- Vérification dans WebKit avec DNG Leica, RAF X-M5 et 3FR Hasselblad : vue
  entière, zoom 100 %, retour à Fit par dézooms répétés, raccourcis Retina,
  recadrage 1:1, grain Strong/Large et comparaison sans film.
- Application macOS reconstruite : les trois RAW passent les contrôles du
  rendu écran à 3 200 pixels, des quatre niveaux de détails, de Classic
  Negative recadré avec grain et commandes optiques Auto, et de la comparaison
  sans film. Les pixels des rendus Leica/Fuji correspondent exactement aux
  références de la version source. Les requêtes de rendus déjà en cache prennent
  3 à 4,4 ms, transfert local compris ; le premier chargement prend 8 à 15 s.

Un RAW jamais chargé nécessite toujours son décodage initial. La première
image peut donc demander plusieurs secondes : cette version privilégie un
premier rendu issu du RAW complet plutôt qu'un aperçu provisoire. Les machines
avec moins de 16 Gio ne préchargent pas le fichier suivant. La résolution
affichable reste celle de l'écran ; le transport est un JPEG sRGB 8 bits et les
exports conservent leurs options séparées. Les effets spatiaux à l'écran sont
adaptés à son échelle et ne constituent pas une preuve de l'export 16 bits.
