# Adaptations photo multimarques — 0.2.29

Les adaptations dérivées des références X-M5 sont maintenant appliquées à
tous les RAW décodables par KŌRA, y compris DNG, CR3, RW2, IIQ et les RAF
des autres boîtiers. Aucun fichier n'est converti en RAF : le traitement agit
après l'entrée commune sRGB linéaire / D65.

## Changements

- Classic Negative reçoit la correction chromatique de 0.2.28, qui préserve
  la luminance et les gris.
- PRO Neg. Hi et Nostalgic Negative utilisent les adaptations photo de
  0.2.27 au lieu des anciens rendus artistiques. Ils deviennent sélectionnables
  pour toutes les sources.
- Color Chrome utilise partout la force réduite mesurée sur le X-M5.
  FX Blue conserve sa réponse précédente.
- Aperçu, zoom, export et simulation utilisée pour l'estimation d'exposition
  partagent ces adaptations. Les métadonnées passent à la révision de rendu 21.
- Le menu et les informations de rendu indiquent « Photo approximation ».

Le grain, la récupération des hautes lumières et les commandes Highlights /
Whites étaient déjà communs aux formats compatibles. Les métadonnées, profils
d'entrée et coefficients de balance des blancs restent propres à chaque source.
Les coefficients de capteur et préréglages WB X-M5 ne sont pas attribués aux
autres appareils. La vue sans simulation continue de contourner les effets.

## Vérifications

Fichiers locaux décodés et rendus avec les trois simulations, puis avec les
quatre combinaisons Highlights/Whites à ±100, grain Strong/Large et Chrome Strong :

| Format | Appareil | Fichier |
|---|---|---|
| DNG | Leica Q3 43 | L1008308 |
| CR3 | Canon EOS R6 Mark II | _86A6942 |
| RW2 | Panasonic DC-S1R | 1100674 |
| IIQ | Phase One iXG 100MP | Kodachrome_IT8 |

28 rendus de contrôle : valeurs finies et dans l'intervalle de sortie attendu.
Comparatifs Classic Negative avant/après inspectés visuellement sur les quatre
sources, ainsi que le DNG avec forte baisse des hautes lumières et blancs.
Empreintes des quatre originaux identiques avant et après les essais.

Les tests vérifient aussi que les mêmes pixels normalisés donnent le même
film et les mêmes effets sans dépendre du nom de l'appareil ; les tuiles sont
identiques à leur région dans le rendu complet. La séparation des corrections
WB propres au capteur conserve ses tests existants.

239 tests Python et 6 tests d'interface réussis. L'application macOS 0.2.29
construite a ouvert L1008308.DNG puis produit un aperçu 1800 × 1197, un rendu
9536 × 6344 et une tuile 512 × 512. Recette : Classic Negative, Highlights −50,
Whites −35, grain Strong/Large, Color Chrome Strong. L'aperçu et un détail du
rendu complet ont été inspectés visuellement.

## Portée des références

La vérification multimarque porte sur le fonctionnement et la stabilité du
traitement. Elle ne mesure pas une fidélité Fuji pour chacun de ces capteurs.
Les coefficients restent issus des cinq scènes X-M5, avec les limites publiées
dans [le bilan 0.2.27](XM5_CALIBRATION.md) et
[le bilan Classic Negative 0.2.28](CLASSIC_NEGATIVE_0.2.28.md).
Ces rendus demeurent des approximations indépendantes ; aucune équivalence
native ni calibration universelle n'est revendiquée.
