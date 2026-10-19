# Réactivité des réglages — version non publiée

## Changements

**Réduction écran réutilisée.** Le rendu écran part toujours du RAW
entièrement décodé, réduit aux pixels physiques de l'écran (moyenne par
boîte), puis corrigé par l'optique si elle est activée. Cette image réduite ne
dépend pas de la recette. Elle est maintenant gardée pour les deux dernières
combinaisons (photo, taille, distorsion, vignetage) : un changement de réglage
ne refait que le rendu. Le cache est propre à la session, borné à deux images
(au plus environ 130 Mio en 4 096 pixels) et rien n'est écrit sur disque.

**Rendus abandonnés interrompus.** Comme les tuiles, chaque rendu écran
porte l'identifiant de la vue et le numéro de révision de la recette. Quand
une révision plus récente arrive, l'ancien rendu s'arrête avant le décodage,
entre les grandes étapes du rendu (tons, film, détails, grain) ou avant
l'encodage JPEG. Avant, le navigateur abandonnait la réponse, mais le serveur
calculait le rendu jusqu'au bout, en concurrence avec le nouveau. Une requête
remplacée (rendu écran ou tuile) reçoit désormais une réponse 409 et
n'écrit plus d'entrée dans le journal de diagnostic.

Le dématriçage, les films, les effets, l'exposition, l'export et le premier
rendu affiché ne changent pas. Le petit aperçu de 1 800 pixels retiré en 0.2.37
n'est pas réintroduit.

## Mesures

Même Mac (M4 Max), interpréteur de distribution, RAW déjà décodé, rendu écran de
3 200 pixels. Suite de cinq recettes : PROVIA, couleur +1, couleur +2,
CLASSIC CHROME, puis recette lourde (Highlights −40, Shadows +30, Clarity +2,
grain faible, Sharpness +1).

| RAW | Version | 1er rendu | Réglages suivants | Recette lourde |
| --- | --- | ---: | ---: | ---: |
| Fuji DSCF5367.RAF | avant | 0,42 s | 0,37 à 0,41 s | 1,13 s |
| Fuji DSCF5367.RAF | après | 0,42 s | 0,26 à 0,30 s | 1,03 s |
| Leica L1005310.DNG | avant | 0,37 s | 0,44 à 0,48 s | 1,19 s |
| Leica L1005310.DNG | après | 0,38 s | 0,30 à 0,34 s | 1,01 s |

Glissement simulé d'un curseur sur L1005310.DNG (recette lourde, une nouvelle
valeur toutes les 150 ms, cinq valeurs) : la dernière valeur est affichée après
**3,12 s avant** et **1,75 s après**. Avant, les quatre rendus abandonnés
allaient tous jusqu'au bout. Après, aucun.

## Vérification

- Les pixels des cinq rendus écran sont identiques bit à bit entre l'ancienne
  et la nouvelle version, sur les deux RAW.
- 289 tests Python et 5 suites JavaScript réussis. Les quatre nouveaux tests
  échouent sur l'ancien code : réutilisation de la réduction avec des pixels
  identiques, rejet avant décodage, interruption entre deux étapes, et réponse
  409 sans diagnostic.
- Non vérifié dans l'application empaquetée ni dans WebKit : le comportement
  de l'interface est couvert par les tests statiques et les mesures serveur
  uniquement.
