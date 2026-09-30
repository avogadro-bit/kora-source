# Hautes lumières et blancs — 0.2.32

Deux problèmes reproduits sur L1007741 et L1003382, avec PROVIA et Classic
Negative, DR100 et des corrections fortes : des transitions cyan/vert dans
les zones partiellement saturées, et des ciels aplatis lorsque Highlights et
Whites RAW sont tous deux à −100.

## Corrections

La reconstruction Leica DNG utilisait des donneurs dont deux couleurs étaient
intactes, alors que la troisième pouvait être saturée. Les estimations de deux
canaux manquants pouvaient donc se contredire. Les donneurs doivent maintenant
avoir leurs trois couleurs intactes. La convolution normalisée reste continue,
sans sélection du voisin le plus proche. La couleur incertaine rejoint aussi
progressivement le neutre à l'approche de la saturation du dernier canal,
au lieu de basculer dans ses derniers 6 %. La luminance est conservée ; aucun
détail n'est inventé dans les zones où le capteur a perdu tous les canaux.

La courbe RAW précédente conservait seulement 1/16 du contraste logarithmique
dans toute la partie haute, aux deux minima combinés. La nouvelle compression
agit sur une transition bornée, avec un plancher de contraste de 18 %, puis
revient à une pente unitaire dans les très hautes lumières. Les nuages gardent
davantage de séparation et les blancs ne restent plus enfermés dans une
longue plage grise. Les deux commandes sélectionnent toujours leur zone sur
l'exposition d'origine, avec une réponse progressive au dixième, des valeurs
intermédiaires monotones et des combinaisons opposées sans inversion des tons.
La conservation bornée des petits détails et les halos des tuiles sont inchangés.

Ce changement privilégie le contraste à une réduction indéfinie : une luminance
linéaire de 16 est ramenée à environ 1,93, contre 0,5 auparavant. Cela évite de
comprimer un ciel entier dans les tons moyens ; les extrêmes peuvent encore
nécessiter DR200/400 ou une baisse d'exposition. DR100 est la protection minimale,
pas la récupération maximale. L'interface le précise maintenant.

La nouvelle courbe RAW est commune aux formats pris en charge. La reconstruction
des canaux concerne le chemin flottant Leica DNG. Les réponses Highlight Tone
et Shadow Tone de 0.2.31 restent inchangées ; ce correctif ne constitue ni un
nouvel étalonnage Fuji ni une équivalence Capture One. La courbe précédente est
conservée exclusivement pour l'estimation d'exposition des recettes de prise
de vue RAF, afin de ne pas déplacer leur point de départ.

Les recettes existantes conservent leurs valeurs. Les corrections RAW négatives
et les couleurs de DNG partiellement saturés peuvent intentionnellement rendre
différemment. La révision de rendu passe à 24.

## Vérification

Comparaisons locales avant/après sur les deux DNG signalés en PROVIA et Classic
Negative : zéro, Highlight Tone −2 et Whites −100, Highlights/Whites RAW −100,
combinaison des minima, DR100 et DR400, puis valeurs RAW intermédiaires.
Contrôle des anciens cas L1003314, L1003412, L1003570, L1008308 et du RAF
DSCF5367. Ces photos privées sont exclues des sources et des distributions.

Tests de non-régression : contamination des donneurs par un troisième canal
saturé, transition progressive de couleur, conservation des canaux survivants,
ordre tonal, contraste des grandes plages claires, précision des réglages,
absence de bord clair sur les transitions fortes, égalité tuiles/image et
stabilité de l'ancrage d'exposition.

Les zones entièrement saturées restent sans texture récupérable. Les couleurs
reconstruites sont des estimations ; la baisse des artefacts n'est pas une mesure
de fidélité à une scène ou à une référence Fuji native.

Sur L1007741, 8,61 % des blocs Bayer ont leurs quatre photosites au niveau
blanc déclaré (16383) ; sur L1003382, 0,38 %. La présence de canaux survivants
ailleurs permet de retrouver une partie de la luminosité, mais pas de mesurer
la couleur perdue. Ces mesures sont distinctes des masques progressifs utilisés
pour la reconstruction.

Livraison : 253 tests Python et 6 tests JavaScript passent. Les sept originaux
conservent leurs empreintes. Le point de départ de DSCF5367 conserve exactement
son estimation d'exposition ; sur les six DNG, le nouvel ajustement chromatique
ne déplace cette estimation que de 0,0054 EV au maximum. L'application macOS
0.2.32 est contrôlée sur les deux DNG signalés et les deux films : aperçus
1800 × 1197, exports 9536 × 6344, tuiles 512 × 512. Sources, installateur,
signature locale et sommes de contrôle sont vérifiés. Les installateurs
précédents restent conservés localement.

Sur ces quatre exports, l'écart moyen entre une tuile et sa région dans
l'image complète est inférieur à 0,002/255. L'aperçu réduit n'est pas une
copie exacte de l'export redimensionné : son écart moyen est de 2,16 à
3,39/255, avec décodage et réduction effectués avant la courbe non linéaire.
