# Highlight Tone et Shadow Tone — 0.2.31

Le X-M5 connecté (firmware 1.20, X RAW STUDIO 1.12) propose deux commandes,
Highlight Tone et Shadow Tone, de −2 à +4 par pas de 0,5, vérifiées dans ses
menus. Les valeurs positives durcissent la zone concernée : hautes lumières
plus brillantes et ombres plus profondes. Les valeurs négatives l'adoucissent.
Il n'existe pas de commandes Whites et Blacks séparées dans ces réglages.
Voir aussi le [manuel X-M5, Tone Curve](https://fujifilm-dsc.com/en/manual/x-m5/menu_shooting/image_quality_setting/).

KŌRA utilisait quatre commandes indépendantes de −100 à +100. L'import de
recette convertissait H en H×25 et S en S×−25, avec arrondi entier. Ces
opérations donnaient la bonne direction générale, mais pas la même courbe,
et perdaient une partie des demi-pas. Elles restent disponibles sous
« RAW recovery · additional controls », avec leur comportement antérieur.
Les deux nouvelles commandes sont affichées dans Light & Contrast.

## Mesures

50 variantes natives déjà acquises et auditées : H puis S à −2, −1, +1, +2,
+4, sur cinq scènes, avec une référence à zéro par scène. Classic Negative,
DR100, WB Auto R0/B0, grain/Chrome/clarté/netteté désactivés, NR −4.
Les MakerNotes vérifient le boîtier, la simulation et les valeurs demandées.
Les photos restent des données locales exclues des distributions.

Deux scènes ajustent les courbes : DSCF5367 (bâtiment/ciel), DSCF5440 (fleurs).
Trois scènes distinctes les contrôlent : DSCF5452 (personne/chien), DSCF5500
(sous-bois ISO 2500), DSCF5512 (plage/ciel). Les variantes et leur référence
native proviennent des mêmes pixels, sans changement de point de vue.

La transformation agit sur la luminance linéaire du rendu, échantillonnée
sur un axe perceptuel sRGB. Une courbe commune par canal a été comparée puis
écartée : elle préservait moins bien les couleurs. Les courbes retenues sont
croissantes et ordonnées selon le réglage. Interpolation PCHIP sur l'axe des
tons, interpolation linéaire entre les niveaux mesurés, identité exacte à
zéro. Un rapprochement vers le gris de même luminance protège les couleurs
qui sortiraient du gamut. Il n'y a ni masque spatial ni voisinage susceptible
de créer les anciennes plaques cyan/magenta.

Pour mesurer la réponse dans KŌRA, on compare la variation par rapport au
rendu zéro à la variation native par rapport au JPEG zéro. Le même recalage
affine sert pour toutes les variantes d'une scène. Images à 640 pixels,
lissage gaussien de 0,7 pixel et exclusion des 12 pixels de bord.

| Moyenne sur les 30 variantes de contrôle | Avant | Après |
|---|---:|---:|
| Écart absolu de réponse RGB, échelle 0–255 | 2,318 | 1,318 |
| Moyenne des écarts médians ΔE00 de l'image complète | 3,046 | 2,956 |

La réduction de 43,2 % concerne **la réponse des commandes**, pas l'erreur
totale du moteur. Appliquée directement au JPEG natif à zéro, la nouvelle
transformation présente un écart moyen de 0,795/255 au JPEG natif modifié.
Cela mesure le modèle de réponse isolé ; ce n'est pas l'écart d'un RAW KŌRA
au moteur Fuji. 46 variantes sur 50 améliorent l'écart de réponse ; quatre
variantes Highlight Tone sur les portraits/sous-bois régressent légèrement
ou modérément. La moyenne s'améliore sur chacune des cinq scènes.

## Intégration et compatibilité

- Nouveaux champs `highlight_tone` / `shadow_tone`, validés de −2 à +4,
  multiples de 0,5. Import des MakerNotes sans multiplication ni arrondi.
- Les anciennes recettes v1/v2 gardent leurs quatre valeurs et reçoivent
  les deux nouveaux champs à zéro. Aucun changement silencieux de rendu.
- L'estimation d'exposition de base conserve explicitement son ancien
  modèle pour ne pas ré-exposer les RAW et invalider les recettes existantes.
- D Range Priority prend le contrôle des réglages manuels comme auparavant ;
  sa propre réponse reste une approximation non mesurée ici.
- Même traitement après la simulation de film pour tous les RAW, y compris
  DNG. Les réglages supplémentaires de récupération RAW restent en amont.
- Traitement par blocs indépendants pour les aperçus, tuiles et exports ;
  pas de motif dépendant de la taille de l'image ni de couture entre tuiles.

## Limites explicites

L'échelle et le sens des commandes sont les mêmes que Fuji. Le rendu n'est
pas identique au moteur propriétaire. La réponse mesurée est celle de
Classic Negative en DR100. Les autres simulations utilisent cette réponse
commune, sans validation native de leurs variations H/S. Les demi-pas sont
interpolés. Les combinaisons H/S composent deux courbes monotones ; aucun
modèle conjoint natif n'est revendiqué. La transformation après simulation
ne recrée pas les détails déjà écrêtés par celle-ci : utiliser au besoin la
récupération RAW supplémentaire en amont.

40 variantes supplémentaires PROVIA/Classic Negative, demi-pas et combinaisons
ont été préparées sur des copies locales, mais leur conversion n'a pas été
validée : l'automatisation de la fenêtre X RAW STUDIO échoue sur la capture
de fenêtre. Ces candidats ne sont pas utilisés comme références mesurées.
`exact_fuji_render` et `calibrated_against_fuji` restent faux ; la révision de
rendu est 23.

## Vérification de livraison

249 tests Python et 6 tests JavaScript passent. Les tests couvrent les 169
combinaisons des demi-pas, la monotonie des gris, le sens des commandes,
les couleurs saturées, l'identité tuiles/image, les recettes anciennes et
l'import des demi-pas. L'interface de l'app construite a été contrôlée avec
Classic Negative, H −1,5 / S +2,5, la désactivation sous D Range Priority,
et la saisie Whites à −0,1 dans le groupe supplémentaire.

Contrôle de stabilité sur L1007724, L1008308, L1003314, L1003412, L1003570
et DSCF5367 : 12 simulations × 7 couples H/S par fichier, valeurs finies
et bornées. Ces contrôles multiformats ne mesurent pas la fidélité Fuji des
simulations non validées. Les empreintes des six originaux sont inchangées.

L'app macOS 0.2.31 produit pour L1007724 un aperçu 1800 × 1197, une image
9536 × 6344 et une tuile 512 × 512 ; pour DSCF5367, un aperçu 1800 × 1200 et
une tuile 512 × 512. Les valeurs H/S de prise de vue du RAF sont importées
à −2/+1, avec les quatre corrections supplémentaires à zéro. Les courbes
sont bien incluses dans l'app et les paquets sources ; aucune photo n'y est
incluse. Les installateurs précédents sont conservés localement.
