# Vérification RAW multimarques — 0.2.34

Campagne du 30 septembre 2026 sur l'application macOS arm64, avec rawpy
0.27.1 / LibRaw 0.22.1. **21 fichiers, 12 modèles, 5 marques et 8 extensions**.
Les 19 échantillons publics viennent de [RAW PIXLS](https://raw.pixls.us/),
sous CC0 ; leurs empreintes SHA-256 ont été vérifiées. Deux photos locales
complètent la campagne (Canon R6 II et Fujifilm X-M5).

## Matrice testée

| Marque | Modèles et variantes | Résultat |
| --- | --- | --- |
| Sony | A7 IV : ARW non compressé, compressé sans perte L, compressé avec perte | 3/3 |
| Nikon | P1000 NRW ; Z6 NEF sans perte ; Z8 NEF sans perte, HE et HE* | 3/5 ; HE et HE* non décodés |
| Canon | 5D IV : CR2 RAW et sRAW ; R5 : CR3 RAW et C-RAW ; R6 II : CR3 | 5/5 |
| Hasselblad | X1D II 50C : FFF ; X2D 100C : 3FR et FFF | 3/3 |
| Fujifilm | X-T5 : RAF non compressé, sans perte et avec perte ; GFX 50S : RAF compressé ; X-M5 : RAF | 5/5 |

Les variantes Nikon HE/HE* restent une limite du décodeur livré. Un message
identifie maintenant cette compression et propose un NEF sans perte/non
compressé ou une conversion DNG avec un logiciel compatible. Cette campagne
ne valide pas cette conversion. Les libellés « 8bit » du catalogue public ne
sont pas utilisés pour décrire ces deux RAW : leurs métadonnées indiquent
High Efficiency et High Efficiency*.

## Contrôles

Pour chaque fichier décodable : découverte dans un dossier, import par fichier,
métadonnées, miniature, aperçu, les douze simulations dont Classic Negative,
réglages combinés aux extrêmes, réponse à ±2 EV, retour à la recette initiale,
détails en vue entière et à 100 %, comparaison sans film, JPEG à pleine
définition avec profil sRGB et TIFF 16 bits recadré. Le TIFF conserve plus de
256 niveaux. Les dimensions des exports correspondent au développement RAW,
qui peut différer du JPEG embarqué. L'export JPEG est comparé à la même région
dans une tuile à 100 %. Taille, date et empreinte des originaux sont inchangées.

Le X2D est développé en 11 664 × 8 750 pixels (102 MP). Son 3FR de 203,43 Mio
révélait une limite d'import de 200 Mio, bien que l'ouverture par dossier et
l'export fonctionnent. La limite passe à **512 Mio**, avec copie en flux sur
disque et rejet des requêtes trop grandes avant lecture du corps.

## Correction visuelle

L'examen des planches a révélé de grandes zones roses dans les hautes lumières
saturées du Nikon P1000, du Z8, du Canon R6 II, et de plus petites zones sur
le Sony A7 IV. Le traitement générique conservait la couleur de canaux perdus
après balance des blancs.

Un masque issu des valeurs du capteur réduit progressivement cette couleur
incertaine lorsque les canaux survivants, pondérés par la balance des blancs,
approchent le blanc. La luminance et les valeurs RAW supérieures au blanc
d'affichage sont conservées. Les pixels non saturés et les couleurs saturées
avec un canal encore sombre ne sont pas neutralisés. Le traitement spécifique
des DNG Leica reste inchangé ; les dispositions autres que Bayer RGBG conservent
leur traitement existant. Il s'agit d'une neutralisation des couleurs perdues,
pas d'une reconstruction des détails brûlés.

Tests automatiques supplémentaires : blanc saturé avec canaux capteur inégaux,
couleur saturée, blanc intact, balance utilisateur, rotation, format non Bayer,
conservation de luminance, de dynamique et du tableau source.

## Reproduire et interpréter

L'inventaire public est dans
[RAW_COMPATIBILITY_SAMPLES.json](RAW_COMPATIBILITY_SAMPLES.json).
Les photos, rendus et rapports personnels restent exclus du dépôt.
`scripts/validate_raw_compatibility.py` teste une application construite via son
API locale. Fournir `--app`, `--out` dans `outputs/`, et `--cases`, un tableau
JSON de fiches `{id, model, mode, path}` avec éventuellement `sha256`.
Les journaux contiennent une session locale et ne doivent pas être publiés.

Ce sont des tests de compatibilité et de cohérence du rendu, **pas un
étalonnage couleur de chaque appareil**, ni une équivalence au moteur Fuji.
Les recettes des JPEG embarqués diffèrent de celles de KŌRA : ces JPEG sont
des repères visuels, pas une cible exacte. Tous les fichiers de cette campagne
ont une orientation capteur normale ; les orientations sont couvertes par
des tests synthétiques, pas par un RAW portrait supplémentaire. La réussite
d'un modèle ou d'une compression ne garantit pas toute la marque. Les RAW
moyen format plus grands, modes pixel-shift, mRAW, autres marques et boîtiers
absents de la matrice restent à tester.
