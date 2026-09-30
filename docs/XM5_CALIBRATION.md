# X-M5 : mesures et corrections 0.2.27

Suite : [optimisation de Classic Negative en 0.2.28](CLASSIC_NEGATIVE_0.2.28.md).
Les conclusions ci-dessous décrivent la version 0.2.27.

KŌRA reste un moteur indépendant. Cette séance apporte des corrections mesurées
sur un X-M5 ; elle ne rend pas tous les réglages ni toutes les simulations
équivalents au boîtier. `calibrated_against_fuji` et `exact_fuji_render` restent
`false`.

## Références acquises

X-M5 firmware 1.20, X RAW STUDIO 1.12. Cinq scènes, 395 variantes uniques
exportées par le boîtier : 49 réglages par scène, 20 simulations/variantes
monochromes par scène, puis 10 modes WB par scène. Les 398 JPEG comprennent
aussi trois exports pilotes/répétés. Provenance et réglages sont contrôlés dans
les MakerNotes, prioritaires sur les tags EXIF génériques. Les fichiers et
profils contenant des identifiants privés restent dans les sorties locales.

- Ajustement : DSCF5367 (architecture/ciel), DSCF5440 (fleurs/végétation).
- Validation séparée : DSCF5452 (personne/chien), DSCF5500 (sous-bois, ISO 2500),
  DSCF5512 (plage/ciel).
- Copies APFS indépendantes ; les empreintes des cinq RAF originaux sont
  identiques avant/après. Aucun firmware ni réglage de prise de vue écrit au
  boîtier.

Le problème initial de pilotage a été résolu en masquant l'arborescence gauche.
Les conversions des deux lots ont été effectuées automatiquement. X RAW STUDIO
est ensuite devenu non réactif ; les essais Kelvin supplémentaires n'ont pas
été validés et ne sont pas utilisés dans le moteur.

## Corrections intégrées

### Balance des blancs

Les libellés complets ExifTool d'ASTIA, PROVIA et Velvia sont reconnus. L'ancienne
estimation d'exposition utilisait PROVIA pour les fichiers ASTIA de cette série.

Sur les RAF X-M5, R/B est maintenant appliqué dans l'espace du capteur. La
matrice est dérivée des données du décodeur ; la vérification indépendante
contre ses sorties RGB capteur et sRGB donne un écart de coefficient inférieur
à 0,0003. Les valeurs signées et la réserve des hautes lumières sont conservées.

Auto reprend l'estimation Auto enregistrée dans le RAF au lieu de neutraliser
la moyenne des couleurs de la scène. Les sept préréglages utilisent les
coefficients X-M5 mesurés, identiques sur les cinq sources, rapportés à la WB
réellement utilisée au décodage. L'aperçu, les tuiles et les exports partagent
ce contexte. Les autres modèles conservent le comportement précédent.

Moyenne des erreurs médianes ΔE00 par variante, sur les trois scènes de
validation (image à 640 pixels, léger lissage, même recalage affine pour toutes
les variantes d'une scène) :

| Groupe | DSCF5452 avant → après | DSCF5500 avant → après | DSCF5512 avant → après |
|---|---:|---:|---:|
| 12 décalages R/B | 4,07 → 3,22 | 4,46 → 3,41 | 4,29 → 2,87 |
| Auto + 7 préréglages | 4,64 → 3,39 | 7,90 → 3,46 | 6,81 → 2,84 |

Ces erreurs incluent les différences résiduelles de dématriçage, d'exposition
et de simulation ; ce ne sont pas des mesures spectrophotométriques.

### Grain

Le nouveau modèle reproduit approximativement l'amplitude et la corrélation
spatiale des différences JPEG Grain On/Off. Il reste déterministe et ne copie
pas le motif aléatoire du boîtier. Le petit grain est plus énergique par pixel ;
le grand grain forme des amas plus larges. Weak et Strong sont mesurés séparément.

À 6240 pixels sur le grand côté, les références réservées donnent environ
0,028–0,034 d'écart type pour Small/Weak et 0,014–0,016 pour Large/Weak ; la
corrélation entre voisins vaut environ 0,14–0,23 et 0,66–0,75 respectivement.
L'amplitude varie encore selon la scène. La protection des noirs/blancs purs
est conservée, même si elle diffère du clipping observé sur le boîtier.
Les vues réduites intègrent le grain, les tuiles utilisent les mêmes coordonnées.

### Simulations et Color Chrome

Les corrections globales des 20 simulations ont été évaluées puis écartées :
leur amélioration sur les scènes d'ajustement ne se généralisait pas assez.
Deux transferts depuis PROVIA, PRO Neg. Hi et Nostalgic Neg., améliorent toutes
les scènes de validation. Ils deviennent sélectionnables pour les RAF X-M5,
avec une mention explicite d'approximation. Les dix LUT officielles existantes
restent inchangées.

| Simulation | DSCF5452 avant → après | DSCF5500 avant → après | DSCF5512 avant → après |
|---|---:|---:|---:|
| PRO Neg. Hi | 6,40 → 4,58 | 6,53 → 4,08 | 2,27 → 1,62 |
| Nostalgic Neg. | 5,49 → 4,13 | 5,56 → 4,17 | 4,32 → 2,31 |

Color Chrome était trop fort sur le X-M5 : son intensité est multipliée par
0,437, ajustée sur deux scènes. L'erreur absolue de l'effet diminue sur les
trois autres, en Weak et Strong. Color Chrome FX Blue reste inchangé : son
facteur mesuré proche de 1 ne justifie pas une nouvelle correction.

## Couverture et limites

| Paramètres | État |
|---|---|
| WB de base / R-B / Auto / préréglages | Corrections intégrées, vérifiées sur X-M5 |
| Grain | Approximation statistique revue sur les paires Fuji |
| PRO Neg. Hi / Nostalgic Neg. | Transfert photo mesuré, limité aux RAF X-M5 |
| Dix LUT officielles / filtres monochromes | Références acquises ; pas d'équivalence complète |
| Color Chrome / FX Blue | Chrome corrigé sur X-M5 ; Blue contrôlé, conservé |
| DR100/200/400, H/S Fuji, couleur | Références acquises ; réponses restent des approximations |
| Netteté, NR, clarté | Références acquises ; pas de modèle natif reproduit |
| Kelvin, Auto White/Ambience en lumière chaude | Non validés ; adaptation précédente conservée |
| Monochromatic Color, Smooth Skin, D Range Priority | Non calibrés par cette séance |
| Formats, tailles, profils ICC, recadrage | Sorties KŌRA indépendantes, pas une copie du JPEG Fuji |
| Optique / HDR / LMO | Restrictions existantes conservées ; LMO et DR Priority indisponibles dans les profils examinés |

Les quatre commandes continues Highlights/Whites/Shadows/Blacks restent celles
de KŌRA. Les paires Fuji H/S ne permettent pas de revendiquer l'équivalence à
Capture One ni une récupération de données absentes du RAW. Les améliorations
des versions 0.2.24–0.2.26 sont conservées.

## Vérification

233 tests automatisés, dont continuité des hautes lumières des deux adaptations,
WB capteur sans clipping intermédiaire, comportement des autres modèles,
statistiques du grain et correspondance aperçu/tuiles. Les mesures de fichiers
réels, rapports de provenance et planches visuelles sont conservés localement
sous `outputs/xm5-calibration`, exclus de la distribution.
