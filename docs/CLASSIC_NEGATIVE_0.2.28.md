# Classic Negative — 0.2.28

Depuis la [version 0.2.29](MULTIRAW_FILMS_0.2.29.md), cette adaptation est aussi
appliquée aux autres RAW. Le bilan ci-dessous décrit sa validation initiale X-M5.

Cette version affine les couleurs de Classic Negative pour les RAF X-M5.
Elle utilise les JPEG de référence produits par le X-M5 firmware 1.20 dans
X RAW STUDIO 1.12, acquis lors de la séance décrite dans
[XM5_CALIBRATION.md](XM5_CALIBRATION.md).
Le moteur reste une approximation indépendante, sans équivalence native.

## Correction

Une petite transformation des composantes a*/b* en CIELAB corrige notamment
les rouges et la végétation après la LUT Classic Negative. L* reste fixe ;
les couleurs qui sortent de sRGB sont ramenées dans le gamut à luminance
constante. Les gris restent identiques. Aucun ajustement global d'exposition
ou de contraste n'est ajouté : les essais de ce type se transféraient mal
entre les scènes.

Le calcul utilise des bandes de lignes pour limiter la mémoire. Aperçu,
export et tuiles de zoom partagent la même transformation. La correction
est limitée aux sources identifiées X-M5. Les autres modèles conservent
leur adaptation précédente. La révision de rendu passe à 20 dans les
métadonnées pour identifier cette nouvelle réponse chromatique.

## Comparaison aux références

Deux scènes servent à l'ajustement ; trois autres servent au contrôle et
à la sélection du modèle, sans être utilisées pour estimer ses coefficients.
Comparaison à 640 pixels, après alignement affine commun à toutes les
variantes d'une scène, léger lissage et exclusion des extrêmes de luminance.
Ces mesures ne sont pas un test de détails ou de bruit à pleine résolution.

Écart médian CIEDE2000, plus petit = plus proche du JPEG X-M5 :

| Scène | Rôle | 0.2.27 | 0.2.28 |
|---|---|---:|---:|
| DSCF5367, architecture | Ajustement | 3,37 | 2,87 |
| DSCF5440, fleurs | Ajustement | 4,02 | 3,62 |
| DSCF5452, portrait/chien | Contrôle | 3,13 | 3,00 |
| DSCF5500, sous-bois | Contrôle | 3,32 | 3,08 |
| DSCF5512, plage | Contrôle | 2,14 | 2,02 |

Les percentiles 90 de cet écart diminuent également sur les cinq rendus de
départ. L'erreur RGB brute augmente légèrement sur deux scènes de contrôle :
le gain concerne la distance perceptuelle choisie, pas toutes les métriques.

245 paires ont été comparées : cinq scènes × 49 variantes, incluant WB R/B,
Highlights, Shadows, DR, couleur, grain, netteté, réduction de bruit et Chrome.
Sur les 147 variantes des trois scènes de contrôle, la moyenne des écarts
médians passe de 3,031 à 2,879, soit environ 5 % de réduction.

## Limites observées

L'amélioration n'est pas uniforme. Neuf variantes de la plage régressent de
plus de 0,1 ΔE médian : DR200/400, Highlights −2/−1, Color −4/−2,
WB R −9/−4 et B −5. Les plus fortes régressions sont Highlights −2 (+0,70)
et R −9 (+0,62). Une variante d'ajustement, Color −4 sur l'architecture,
régresse de +0,18. Ces écarts sont conservés dans le bilan, pas masqués par
la moyenne. L'augmentation de l'ensemble d'ajustement avec les WB extrêmes
n'a pas résolu ce problème et n'a pas été retenue.

Il reste des différences de contraste, de réponse aux réglages et de ciel
par rapport au boîtier. Cinq scènes ne constituent pas une calibration
universelle. `calibrated_against_fuji` et `exact_fuji_render` restent faux.

## Vérification logicielle

237 tests automatisés passent, dont conservation de luminance, identité
des gris, continuité des rampes de couleurs/hautes lumières, identité entre
tuile et image entière et stabilité avec Highlights/Whites à ±100.
L'application macOS construite a ouvert DSCF5367.RAF et produit un aperçu
1800 × 1200, un rendu 6264 × 4176 et une tuile 512 × 512 avec Classic Negative,
WB Daylight R+4/B−5, grain Strong/Large et Color Chrome Strong. Aperçu et tuile
ont également été inspectés visuellement.
Les références privées et sorties de comparaison restent hors du paquet
source et de l'application distribuable.
