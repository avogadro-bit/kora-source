# Leica Q3 43 / X-M5 — ajustement 0.2.30

L1007724.DNG (Leica Q3 43) et DSCF5367.RAF (X-M5) représentent le même
bâtiment depuis des points de vue différents. Cette paire sert à affiner
l'entrée des DNG Q3 43, avant les simulations et les réglages de recette.
Il ne s'agit pas d'une calibration universelle des DNG ou des boîtiers Leica.

## Référence et méthode

X RAW STUDIO affiche actuellement le RAF avec ASTIA, DR400, R+4/B−5,
Highlights −2, Shadows +1, Color +4 et plusieurs effets forts. Ce rendu de
recette n'est pas une référence neutre pour la conversion d'un autre capteur.
Les exports X-M5 déjà acquis dans X RAW STUDIO 1.12 / firmware 1.20 fournissent
les versions de contrôle sans ces décalages : DR100, WB R0/B0, réglages neutres,
grain et Chrome désactivés, NR −4.

270 correspondances géométriques robustes permettent de relier la façade
visible dans les deux photos. L'échantillonnage est limité à la surface
commune, en excluant le ciel, la majeure partie des branches en avant-plan
et les incohérences de luminosité dues aux occlusions/reflets. Les vitrages,
la parallaxe résiduelle et les reflets restent des sources d'incertitude.
996 échantillons sont conservés : 414 pour l'ajustement, 582 dans d'autres
bandes de façade pour le contrôle. Ce sont des zones distinctes d'une même
scène, pas des photographies indépendantes.

Une différence d'exposition de −0,364 EV est estimée sur les zones d'ajustement
pour comparer les couleurs à luminosité rapprochée. Elle est identique pour
les mesures avant/après et n'est pas appliquée au profil du boîtier.
Les matrices de couleur plus générales ont été rejetées : elles n'amélioraient
pas régulièrement les zones de contrôle.

## Correction retenue

Gains RGB dans l'espace de travail linéaire :
`[1.0018982841, 1.0, 0.9798716044]`.
Cela diminue légèrement le bleu, avec une très petite augmentation du rouge.
C'est un ajustement de point blanc dérivé de cette paire en lumière du jour,
pas une reconstruction de la réponse spectrale du capteur.

Le profil `leica-q3-43-reference-v1` exige à la fois une entrée DNG, une marque
Leica et le modèle exact Q3 43. Q3, Q2, M11, DNG Apple et RAW des autres marques
ne reçoivent pas ces coefficients. La conversion flottante Leica existante
est conservée. Les mêmes gains sont appliqués une seule fois, après
l'estimation d'exposition, en aperçu et en pleine résolution. Les valeurs
négatives et supérieures à 1 ne sont pas écrêtées. L'exposition de la recette
reste à zéro par défaut.

## Mesures sur les zones de contrôle

Écart médian CIEDE2000 au JPEG natif X-M5, après l'alignement d'exposition
propre à cette paire. Ajustement effectué avec PROVIA uniquement :

| Simulation | Avant | Après |
|---|---:|---:|
| PROVIA | 3,249 | 3,172 |
| Classic Negative | 3,732 | 3,549 |
| ASTIA | 4,174 | 4,034 |
| Velvia | 4,424 | 4,039 |
| Classic Chrome | 3,834 | 3,807 |
| PRO Neg. Std | 3,387 | 3,324 |
| PRO Neg. Hi | 3,367 | 3,303 |
| Nostalgic Negative | 2,846 | 2,765 |

Le gain est faible mais cohérent sur ces huit simulations. Ces chiffres ne
mesurent ni l'ensemble du ciel, ni la fidélité sur d'autres éclairages.
La différence d'angle de prise de vue rend une comparaison globale des pixels
inappropriée. Le ciel n'a pas été artificiellement ramené à la couleur de
l'autre photographie.

## Validation et limites

La correction est également vérifiée sur L1008308 (chien), L1003314 (rue
fleurie), L1003412 et L1003570 (ciels/végétation), avec PROVIA, Classic Negative,
ASTIA et les quatre combinaisons Highlights/Whites à ±100. Ces autres scènes
servent au contrôle de stabilité, sans référence Fuji simultanée permettant
de revendiquer une amélioration colorimétrique mesurée.

241 tests Python et 6 tests d'interface passent. Ils couvrent notamment la
sélection exacte du modèle, l'identité aperçu/pleine résolution, l'application
unique du profil et la préservation de la réserve RAW. Les fichiers originaux
sont vérifiés par empreintes ; photographies et calculs privés restent exclus
des paquets distribuables. La révision de rendu passe à 22.

L'application macOS construite confirme le profil attendu pour L1007724.DNG
et produit un aperçu 1800 × 1197, un rendu 9536 × 6344 et une tuile 512 × 512.
Le rendu d'aperçu Classic Negative a été inspecté visuellement.

La recette locale `L1007724-reference-recipe.json` propose séparément PROVIA et
−0,36 EV pour cette photo précise. Elle ne modifie pas les autres DNG.
`fuji_color_calibrated` reste faux et les métadonnées signalent explicitement
la limite à une paire diurne.
