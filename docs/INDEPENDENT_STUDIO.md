> État historique : le profil artistique v2 décrit ci-dessous a été remplacé par les [LUT officielles du GFX ETERNA 55](OFFICIAL_LUT_STUDIO.md) pour dix films.

# Moteur indépendant v1

`kora/studio.py` effectue le décodage LibRaw en sRGB linéaire, la balance caméra, une adaptation RGB relative pour les réglages WB, l’exposition et la compression des hautes lumières, puis les transformations de style et les effets spatiaux. Les coefficients sont des choix artistiques explicites, pas des tables Fuji récupérées ni un apprentissage sur références. Classic Negative modifie contraste, saturation, verts, rouges et teintes des ombres/hautes lumières.

Le moteur natif reste dans `engine.py` ; ses refus de rendu exact sont conservés. `StudioRecipe` étend le schéma historique sans modifier ses valeurs et validations pour la recherche native.

## Aperçu et export

Les modifications de recette utilisent d'abord un aperçu linéaire mis en cache et limité à 1 800 pixels. Chaque vue, même sans zoom, charge ensuite des régions détaillées issues du RAW complet, à une résolution adaptée aux pixels physiques de l'écran. Le zoom 100 % correspond à un pixel de photo par pixel physique, y compris sur Retina. Les régions visibles sont conservées pendant les déplacements et les changements de zoom. Les réponses d'une ancienne photo ou recette sont ignorées. Le tableau linéaire pleine définition reste réutilisable par l'export. Attendre « Image ready » pour juger la netteté. Voir [les vérifications et limites d'affichage](DISPLAY_0.2.33.md).

L’export travaille toujours à pleine définition et produit JPEG avec ICC ou TIFF RGB 8/16 bits avec ICC et recette dans la description. Adobe RGB utilise une conversion matricielle D65 depuis le sRGB linéaire et son gamma ; le profil macOS est incorporé. Les couleurs déjà écrêtées dans le traitement sRGB ne sont pas récupérées par l’export Adobe RGB. Les TIFF 16 bits conservent la précision flottante jusqu’à la quantification finale.

Le traitement n’applique pas les tables locales propriétaires Apple ProRAW et n’offre pas la même interprétation que Photos. La balance Kelvin est une adaptation relative de RGB déjà équilibrés ; ce n’est pas une reconstruction spectrale du capteur. Le lissage de peau utilise un masque de couleur, sans détection de visage.

## Validation du 14 septembre 2026

- 74 tests passent, comprenant l’effet des recettes via HTTP, la conservation du tableau source, le grain déterministe, les canaux monochromes, les limites de paramètres, le recadrage, la précision TIFF 16 bits et la conversion Adobe RGB comparée à LittleCMS.
- Développements réels vérifiés sur `DSCF2344.RAF` (X100VI), `20260621_0001.DNG` (Leica) et `IMG_4768.DNG` (Apple ProRAW). Aperçus et variations dans `outputs/independent-studio/`.
- Export réel du RAF : 7752 × 5178, TIFF uint16 RGB, profil ICC présent, environ 230 Mio et 17,8 secondes sur ce Mac lors de ce contrôle.
- Vérification visuelle du GUI local : photo, Classic Negative sélectionné, modification de l’exposition, panneau de développement et état « Recette appliquée ».

Ces contrôles prouvent le fonctionnement du rendu indépendant, pas une correspondance au moteur Fuji. Les données de référence nécessaires à une calibration comparative n’ont pas été constituées.
# Correction Classic Negative — profil v2

Le profil initial produisait une différence moyenne absolue de seulement 0,016
sur le DNG de paysage et 0,009 sur le RAF nocturne, en RGB sRGB normalisé.
Le profil v2 renforce la courbe des tons, les verts olive, les rouges chauds et
les bleus. Il reste une interprétation artistique non calibrée contre Fuji.
La courbe conserve les extrémités et une progression monotone des gris.
Les recettes Classic Negative existantes utilisent désormais ce profil, aussi
bien pour l’aperçu que pour l’export. Les autres films ne changent pas.

Validation : 76 tests réussis, dont deux nouveaux tests de contraste et couleur.
Comparatifs locaux : `outputs/classic-negative-fix/comparison.jpg` ; mesures
dans `outputs/classic-negative-fix/metrics.json`. Ces écarts mesurent la force
du traitement par rapport au neutre, pas sa fidélité à Fujifilm.
