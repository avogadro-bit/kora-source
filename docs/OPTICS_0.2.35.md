# Profils optiques — 0.2.35

La base officielle [Lensfun](https://lensfun.github.io/lenslist/) du
24 septembre 2026 est intégrée à KŌRA, au format 1 compatible avec le moteur
livré. Elle contient **1 569 profils** (1 470 noms d'objectifs distincts) et
**1 057 références de boîtiers**, contre 1 304 profils et 948 boîtiers dans la
base de lensfunpy 1.18.0 utilisée précédemment. Certaines optiques ont plusieurs
profils selon le format du capteur. Le nombre de profils ne signifie pas que
tous possèdent à la fois distorsion et vignettage à toutes les focales.

## Reconnaissance et proposition

- Lecture du nom d'objectif et des identifiants résolus par ExifTool. Un nom
  de fabricant numérique ou ambigu (« … or … ») ne devient pas une certitude.
- Recherche stricte limitée aux montures compatibles du boîtier reconnu.
  Les noms commerciaux proches et les versions I/II/III ne sont pas confondus.
- Pour un boîtier à objectif intégré, utilisation de sa monture privée Lensfun
  si elle détermine un seul objectif, avec vérification de la focale. Ce
  mécanisme ne s'applique pas aux boîtiers à objectifs interchangeables.
- Si un même objectif possède plusieurs profils de capteur, choix de la
  calibration la plus proche uniquement si son identité est la même et le
  choix unique.
- L'interface indique le nom reconnu et les corrections disponibles. Le
  bouton **Apply available corrections** active uniquement celles-ci, avec
  annulation possible. Les commandes séparées restent accessibles ; une
  recette existante n'est pas modifiée au simple chargement d'une photo.

L'application utilise la même base et la même correspondance pour l'aperçu,
les détails du zoom et l'export. Les fichiers XML, la licence CC BY-SA 3.0 et
`origin.json` accompagnent le dépôt, les distributions Python et les applications
macOS/Windows. La date et l'empreinte de l'archive officielle permettent de
reproduire la version de la base ; aucun téléchargement de profils n'est
déclenché à l'ouverture d'une photo.

## Cas réels et limites

La série RAW multimarques précédente sert à vérifier la reconnaissance et
les rendus corrigés. Les cas nouvellement reconnus comprennent :

| RAW | Objectif / profil |
| --- | --- |
| Fujifilm X-M5 | XC15–45 mm F3.5–5.6 OIS PZ |
| Canon EOS R5 | Sigma 50 mm F1.4 DG HSM Art |
| Nikon P1000 | Objectif intégré, profil P1000 & compatibles |

Le X100VI est également identifié dans la nouvelle base avec le profil de sa
famille d'objectif intégré ; sa correspondance est couverte par un test de
métadonnées. Les contrôles de non-régression couvrent aussi le Nikon Z6/Z8,
le Sony A7 IV, le Fujifilm X-T5 et le Canon R6 II. Un boîtier peut avoir un
profil optique tout en utilisant une compression RAW non décodable, notamment
les Z8 HE/HE*.

L'application macOS construite a passé 300 contrôles sur 12 RAW réels : neuf
avec une correction disponible (dont le DNG Leica) et trois sans profil
fiable. Douze simulations, dont Classic Negative, ont été rendues ; les
détails à 100 %, le JPEG pleine définition et le TIFF 16 bits ont été relus.
L'écart moyen tuile/JPEG reste inférieur à 5 niveaux sur 255 sur les régions
comparées. Les originaux ont conservé leurs empreintes. Le catalogue a aussi
fourni 3 059 cartes de distorsion finies aux focales minimale, médiane et
maximale ; ce contrôle numérique n'est pas une mesure de précision sur mire.
Les 265 tests Python et 15 tests JavaScript passent. Dans l'interface finale,
activation, annulation et absence de proposition pour le XCD 38V ont été
vérifiées directement.

Les échantillons Hasselblad XCD 21/38V et Fujifilm GF63 mm restent sans profil
dans cette base. Le Canon 5D IV indique un 24–70 mm dont l'identifiant est
partagé entre Sigma et Tamron : aucune des deux calibrations n'est choisie.
Les RAW restent lisibles sans correction optique dans ces cas.

Le traitement DNG Leica validé est conservé. Les DNG déjà transformés ou non
validés restent exclus de l'automatisme pour éviter une seconde correction.
Les modèles ACM du format 2 de Lensfun ne sont pas pris en charge par le
moteur livré. Les aberrations chromatiques ne sont pas activées par ce bouton.
Le vignettage conserve l'hypothèse existante de mise au point lointaine ; il
peut rester approximatif à courte distance. Ce travail élargit la couverture
des profils publiés ; il ne constitue pas un nouvel étalonnage sur mire de
chaque objectif.
