# Chargement RAW multi-cœur — 0.2.44

## Changements

**Décodeur RAW sur tous les cœurs (Mac Apple Silicon).** La wheel rawpy de PyPI
pour macOS compile LibRaw sans OpenMP : le dématriçage, surtout celui des
capteurs Fujifilm X-Trans (Markesteijn, 3 passes), n'utilisait qu'un cœur.
L'app embarque désormais rawpy 0.27.1 / LibRaw 0.22.1 recompilé avec OpenMP par
`scripts/build_rawpy_openmp.py` : mêmes versions et options de codecs que la CI
de rawpy (libjpeg-turbo 3.1.3, JasPer 4.2.5, Little CMS 2.11), runtime OpenMP de
LLVM 22.1.8, cible macOS 14, sources vérifiées par SHA-256, aucune bibliothèque
Homebrew. La version embarquée est marquée `0.27.1+kora.xtrans1` et la
construction de l'app refuse toute autre wheel sur Apple Silicon.

**Résultat identique et reproductible.** Avec OpenMP, LibRaw 0.22.1 ne donnait
pas toujours le même résultat pour un fichier X-Trans : en pleine résolution,
une rangée de tuiles du dématriçage lisait 8 lignes que la rangée précédente
pouvait être en train d'écrire ; en demi-taille (aperçu servant à caler
l'exposition), plusieurs threads écrivaient le même pixel. Mesuré sur cinq RAF :
toute l'image changeait d'une exécution à l'autre (écart moyen 2×10⁻⁵, jusqu'à
0,66 en valeur linéaire sur quelques pixels). `packaging/libraw-xtrans-deterministic-openmp.patch`
fait attendre chaque tuile que les tuiles voisines de la rangée précédente soient
terminées (une tuile lit au plus 6 pixels autour d'elle, les recouvrements font
16 pixels) et confie à un seul thread chaque ligne de l'aperçu demi-taille.
Le résultat est alors exactement celui de LibRaw mono-thread.

La wheel rawpy officielle pour **Windows** utilisait déjà OpenMP sans ces
corrections : les X-Trans pouvaient y varier d'une ouverture à l'autre. La
construction Windows utilise maintenant le même patch (voir `WINDOWS_RELEASE.md`).
Le Mac Intel garde son décodeur mono-thread de 0.2.43, déterministe.

**Rendus d'écran abandonnés interrompus.** Comme les tuiles, chaque rendu écran
porte l'identifiant de la vue et le numéro de révision de la recette. Quand un
réglage plus récent arrive, l'ancien rendu s'arrête avant le décodage, entre les
grandes étapes du rendu (tons, film, détails, grain) ou avant l'encodage. Une
requête remplacée reçoit une réponse 409 et n'écrit plus de diagnostic.

Films, effets, exposition, exports, cache de la réduction écran (0.2.43) et
premier rendu affiché ne changent pas.

## Mesures

Apple M4 Max (14 cœurs), interpréteur de distribution, nouveau processus pour
chaque campagne. « Avant » : rawpy 0.27.1 de PyPI ; « Après » : rawpy
`0.27.1+kora.xtrans1`. Temps du décodage KŌRA complet (`decode(preview=False)`,
calage d'exposition compris) ; pixels du RAW linéaire float32 comparés par
SHA-256, en pleine résolution et en aperçu ; la version modifiée est décodée
deux fois pour vérifier qu'elle est déterministe.

| RAW | Mpx | Avant | Après | Gain | Identique (complet / aperçu) | Déterministe |
| --- | ---: | ---: | ---: | ---: | :---: | :---: |
| Fujifilm · GFX 50S · 14bit 14bit compressed 3:2.RAF | 51,4 | 5,29 s | 2,75 s | 1,9× | oui / oui | oui |
| Nikon · COOLPIX P1000 · 12bit 12bit uncompressed 4:3.NRW | 16,0 | 1,17 s | 0,99 s | 1,2× | oui / oui | oui |
| Nikon · Z 6 · 14bit 14bit lossless compressed 3:2.NEF | 24,5 | 2,05 s | 1,80 s | 1,1× | oui / oui | oui |
| Hasselblad · X1D II 50C · 16bit 4:3.fff | 51,4 | 2,86 s | 2,19 s | 1,3× | oui / oui | oui |
| Canon · EOS R5 · 3_2.CR3 | 44,7 | 3,51 s | 2,47 s | 1,4× | oui / oui | oui |
| Canon · EOS R5 · 3_2.CR3 | 44,7 | 2,20 s | 1,24 s | 1,8× | oui / oui | oui |
| Fujifilm · X-T5 · 14bit 14bit compressed 3:2.RAF | 40,1 | 14,29 s | 4,13 s | 3,5× | oui / oui | oui |
| Fujifilm · X-T5 · 14bit 14bit compressed 3:2.RAF | 40,1 | 14,62 s | 3,87 s | 3,8× | oui / oui | oui |
| Fujifilm · X-T5 · 14bit 14bit uncompressed 3:2.RAF | 40,1 | 12,59 s | 3,65 s | 3,5× | oui / oui | oui |
| Hasselblad · X2D 100C · 16bit 4:3.3FR | 102,1 | 6,02 s | 4,77 s | 1,3× | oui / oui | oui |
| Hasselblad · X2D 100C · 16bit 4:3.fff | 102,1 | 8,41 s | 7,13 s | 1,2× | oui / oui | oui |
| Nikon · Z 8 · 8bit 8bit compressed 3:2.NEF | — | non pris en charge | non pris en charge | — | même erreur : oui | — |
| Nikon · Z 8 · 8bit 8bit compressed 3:2.NEF | 45,7 | 3,79 s | 3,10 s | 1,2× | oui / oui | oui |
| Nikon · Z 8 · 8bit 8bit compressed 3:2.NEF | — | non pris en charge | non pris en charge | — | même erreur : oui | — |
| Sony · ILCE-7M4 · 14bit 14bit uncompressed 3:2.ARW | 32,9 | 2,16 s | 1,62 s | 1,3× | oui / oui | oui |
| Sony · ILCE-7M4 · 14bit 4:3.ARW | 32,9 | 2,74 s | 2,23 s | 1,2× | oui / oui | oui |
| Sony · ILCE-7M4 · 14bit 3:2.ARW | 32,9 | 2,22 s | 1,71 s | 1,3× | oui / oui | oui |
| Canon · EOS 5D Mark IV · sRAW2 _sRAW_ 3:2.CR2 | 7,5 | 0,70 s | 0,68 s | 1,0× | oui / oui | oui |
| Canon · EOS 5D Mark IV · RAW 3:2.CR2 | 30,4 | 2,55 s | 2,08 s | 1,2× | oui / oui | oui |
| DSCF5367_00_baseline.RAF | 26,2 | 9,98 s | 4,50 s | 2,2× | oui / oui | oui |
| L1005310.DNG | 60,5 | 7,81 s | 6,76 s | 1,2× | oui / oui | oui |
| _86A7139.CR3 | 24,2 | 1,97 s | 1,39 s | 1,4× | oui / oui | oui |
| DSCF5048.RAF | 26,2 | 8,82 s | 3,51 s | 2,5× | oui / oui | oui |

Ouverture d'une photo jusqu'au premier rendu écran complet (3 200 pixels),
inspection et décodage lancés ensemble comme dans l'interface, médiane de trois
campagnes, code 0.2.43 + rawpy PyPI contre 0.2.44 :

| RAW | 0.2.43 | 0.2.44 |
| --- | ---: | ---: |
| Fujifilm X-M5 DSCF5367.RAF, 26 Mpx | 8,37 s | 3,16 s |
| Fujifilm X-T5 6122.RAF, 40 Mpx | 13,02 s | 3,93 s |
| Leica L1005310.DNG, 60 Mpx | 5,79 s | 5,09 s |
| Canon _86A7139.CR3, 24 Mpx | 1,72 s | 1,33 s |

Glissement simulé d'un curseur sur L1005310.DNG (recette lourde : Highlights −40,
Shadows +30, Clarity +2, grain faible, Sharpness +1, Color Chrome fort ; une
valeur toutes les 150 ms, cinq valeurs) : dernière valeur affichée après
2,95 à 3,02 s en 0.2.43, 1,72 à 1,79 s en 0.2.44. En 0.2.43, les quatre rendus
abandonnés allaient au bout ; en 0.2.44, aucun.

## Vérification

- 21 RAW lisibles de 11 appareils (Fujifilm X-M5, X-T5 et GFX 50S, Leica, Canon
  R5 et 5D Mark IV, Nikon Z 6, Z 8 et P1000, Sony A7 IV, Hasselblad X1D II et
  X2D) : RAW linéaire et aperçu identiques bit à bit au décodeur d'origine, et
  identiques entre deux exécutions. Les deux NEF Z 8 non pris en charge
  échouent avec la même erreur dans les deux versions.
- Avant le patch, les cinq RAF X-Trans différaient ; après, aucun.
- 327 tests Python et 5 suites JavaScript réussis, dont l'application du patch
  aux sources rawpy épinglées et le refus d'une wheel OpenMP non corrigée.
- Les bibliothèques de la wheel déclarent au plus macOS 14 (14.0, et 11.0 pour
  l'extension Python) et se chargent depuis la wheel (`@loader_path`), sans
  chemin absolu externe.

L'app macOS 0.2.44 construite localement embarque `rawpy 0.27.1+kora.xtrans1`
(vérifié par la construction), un seul runtime libomp et les notices LLVM et
du patch. Son audit couvre 140 binaires (macOS 14, arm64) et sa signature ad hoc
est vérifiée. `scripts/smoke_macos_release.py` réussit avec le RAF X-T5 6122
déplacé dans un chemin Unicode : aperçu Kodachrome, tuile 512 × 512 et export
7752 × 5178 avec profil ICC, RAW d'origine inchangé. Dans l'app empaquetée, le
RAF X-M5 s'ouvre en 2,15 s et son premier rendu écran complet suit 3,13 s plus
tard ; les réglages suivants prennent 0,27 à 0,28 s. La fenêtre native n'est pas
testée par script.

## Limites

Mesures sur un seul Mac haut de gamme : le gain dépend du nombre de cœurs.
L'ordonnancement limite le parallélisme du dématriçage X-Trans à environ une
rangée de tuiles par cœur, d'où 3,5× plutôt que le 6× d'OpenMP sans ordre.
Les DNG et autres capteurs Bayer gagnent moins : leur coût est surtout dans le
traitement KŌRA en Python, pas dans LibRaw. La construction Windows avec le
patch est prête mais n'a pas encore tourné : elle doit passer sur le runner
GitHub Windows avant toute distribution.
