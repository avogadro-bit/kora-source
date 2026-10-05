# Chargement RAW — 0.2.38

## Optimisations

L'estimation de l'exposition Fuji effectuait plusieurs rendus de référence
avec la même texture de grain. Sur DSCF5367, dix calculs de cette texture
occupaient presque treize secondes. Les petits champs de grain sont désormais
réutilisés entre expositions et intensités, sans réutiliser les pixels de la
photo. Le cache distingue dimensions, taille du grain, échelle et origine ;
il contient au plus huit champs de 256 × 256 pixels, soit 2 Mio.

Les trois estimations de couleur des hautes lumières DNG sont calculées en
parallèle à petite résolution. Les grandes images intermédiaires restent
traitées en série pour limiter la mémoire. La conversion matricielle et la
neutralisation des couleurs incertaines utilisent des bandes de lignes et le
pool de calcul partagé. Cela évite plusieurs copies complètes du RAW.

Le dématriçage, les courbes, les films, le modèle de grain, la balance des
blancs et la définition du premier rendu ne changent pas. Les optimisations
de l'affichage et la butée de zoom de 0.2.37 restent présentes. Aucun cache
persistant de photographies n'est créé sur disque.

## Mesures

Mesures locales avec le même interpréteur de distribution et un nouveau
processus par campagne, PROVIA, réduction de bruit −4, grain désactivé dans la
recette d'affichage. Le grain de la prise de vue reste utilisé dans la
référence d'exposition. Le cache disque du système n'est pas purgé.
L'intervalle comprend inspection, décodage complet et JPEG écran de 3 200
pixels ; il exclut le transfert et l'affichage WebKit.

Médianes de trois ouvertures par version, sans cache Kora préalable :

| RAW | 0.2.37 | 0.2.38 | Gain |
| --- | ---: | ---: | ---: |
| Leica L1007741.DNG | 8,40 s | 6,09 s | 28 % |
| Fuji X-M5 DSCF5367.RAF | 14,26 s | 8,57 s | 40 % |
| Hasselblad X2D 6565.3FR | 6,68 s | 6,78 s | Pas de gain mesurable |

Les valeurs Hasselblad varient de 6,26 à 6,85 s avant et de 5,63 à 7,76 s
après : cette optimisation ne démontre pas d'accélération sur ce fichier.
Sur les trois fichiers, une nouvelle tuile à 100 % demande environ 38 à
45 ms après chargement ; un rendu écran en cache est retrouvé en moins de
1 ms côté serveur. Ces mesures ne sont pas des délais complets de clic.

## Vérification

Les contrôles automatisés vérifient la réutilisation du grain sans mélanger
expositions, forces ou coordonnées, sa limite mémoire, et l'identité de la
conversion DNG par bandes avec la formule appliquée à l'image entière.

273 tests Python et 16 tests JavaScript réussis. Comparaison avec la version
0.2.37 sur huit RAW : deux Leica DNG, Fuji X-M5 et X-T5 RAF, Hasselblad X2D
3FR, Sony A7 IV ARW, Nikon Z6 NEF et Canon R5 CR3. Les tableaux complets
float32 et les expositions sont identiques bit à bit. Les seize rendus de
contrôle PROVIA/Classic Negative, avec récupération des hautes lumières,
DR400, recadrage carré et grain Strong/Large, le sont également. Les
empreintes des fichiers originaux restent inchangées.

L'application macOS 0.2.38 empaquetée passe également les contrôles sur
Leica, Fuji et Hasselblad : rendu écran, quatre niveaux de tuiles, recadrage
carré Classic Negative avec grain, corrections optiques Auto et comparaison
sans film. Ses rendus écran correspondent exactement à ceux de 0.2.37. Les
premières vues prennent respectivement 5,57 s, 8,78 s et 5,88 s dans cette
campagne de contrôle ; les réponses déjà en cache prennent 2,6 à 3,5 ms,
transfert local compris. La signature ad hoc de l'application est vérifiée.

Le premier décodage d'un RAW reste nécessaire. Les gains dépendent du
fichier ; les RAF dont le dématriçage domine et les grands RAW moyen format
peuvent encore demander plusieurs secondes avant leur première vue complète.
