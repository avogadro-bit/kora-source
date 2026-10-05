# Points multicolores après recadrage — 0.2.36

## Cause et correction

Le défaut est reproduit dans la vue détaillée sur les échantillons publics
X-T5 RAF 6124 (ratio 3:2) et Hasselblad X2D 100C 3FR 6565 (ratio 1:1), avec
Velvia, grain Strong/Large et commandes optiques sur Auto. Le XCD 38V du
Hasselblad reste sans profil, donc sans correction optique effective.

Certains recadrages ne sont pas alignés sur la grille des aperçus réduits.
Le rééchantillonnage Lanczos ajuste alors les pixels après leur rendu. Ses
lobes peuvent produire des valeurs légèrement négatives ou supérieures à 1.
La conversion directe en entier non signé faisait reboucler ces valeurs :
un canal sombre devenait très clair, ou inversement. Le grain et les bords
contrastés rendaient ces points multicolores particulièrement visibles.
La même conversion pouvait affecter les exports redimensionnés en M ou S.

La conversion finale commune borne désormais les valeurs à l'intervalle
du format entier avant leur conversion. Elle couvre les aperçus JPEG, les
détails de zoom, le JPEG exporté et les TIFF 8/16 bits. Elle ne modifie pas
les tableaux sources. Les valeurs signées et HDR en amont, la latitude RAW,
les courbes de film, le grain et les dimensions de sortie sont préservés.

## Vérifications

- Deux tests de régression échouaient avant la correction sur sept cas
  d'encodage : aperçus, JPEG, TIFF 8 bits et TIFF 16 bits. Ils passent après
  correction ; la suite Python complète comporte 267 tests réussis.
- Sur les deux zones RAW reproduisant le défaut, respectivement 5 607 et
  30 265 pixels présentaient une erreur de canal supérieure à 64/255 avant
  correction. Après correction, aucun pixel ne présente cette erreur par
  rapport à la référence dont les valeurs de sortie sont bornées.
- L'application macOS 0.2.36 reconstruite produit les mêmes pixels que ces
  deux références corrigées, comparés après décodage du JPEG d'aperçu.
- L'application passe 40 contrôles de tuiles : deux RAW, cinq ratios
  (Original, 1:1, 16:9, 4:3, 3:2) et quatre niveaux de résolution. Les
  dimensions et profils ICC sont relus, puis le retour au premier ratio
  est vérifié identique.
- Sur chacun des deux RAW, un JPEG M et un TIFF 16 bits S recadrés en 1:1
  sont exportés et relus. Dimensions et précision TIFF sont vérifiées.
- Les empreintes SHA-256 des originaux restent identiques.

Ces contrôles ciblent le défaut de conversion et les chemins de sortie.
Ils ne constituent pas une nouvelle calibration des couleurs ou du grain.
