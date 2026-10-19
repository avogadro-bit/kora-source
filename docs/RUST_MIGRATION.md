# Migration vers Rust + Tauri — analyse, mesures et plan

Version analysée : KŌRA 0.2.41 (branche `codex/windows-0.2.41`). Les mesures de
la section 3 datent de cette version ; la 0.2.43 a ensuite ajouté son propre cache
de la réduction écran, et la 0.2.44 le décodeur multi-cœur (voir la section 4).
Objectif : une application **Windows et macOS**, puis **iPad** plus tard.
Mesures faites le 18 octobre 2026 sur un Apple M4 Max (14 cœurs, 36 Go). Sur un
portable Windows courant, il faut s'attendre à des temps 2 à 4 fois plus longs.

## 1. Décision

**Cœur de traitement en Rust + application Tauri 2 qui réutilise l'interface
HTML/JS actuelle.** Python reste l'outil de recherche et de calibration.

| Option | Windows + Mac | iPad | Réutilise l'UI | Verdict |
|---|---|---|---|---|
| Rester en Python (pywebview + PyInstaller) | oui, mais packaging fragile | **non** | oui | impasse pour l'iPad |
| Swift natif | non (pas de Windows) | oui | non | exclu |
| Electron + cœur natif | oui | non | oui | lourd, pas d'iPad |
| Rust + UI native (egui, Slint, iced) | oui | partiel | **non** | réécrire l'UI pour rien |
| **Rust + Tauri 2** | **oui** | **oui (cible iOS de Tauri 2)** | **oui** | **retenu** |

Ce que ça apporte concrètement :

- **Distribution** : un exécutable natif d'environ 15 à 30 Mo au lieu de 113 Mo
  (dont 18 Mo pour `libpython`, plus Tcl/Tk, SciPy et Pydantic). Il n'y a plus de
  runtime Python à embarquer, plus de wheels à épingler par architecture, plus
  de problèmes d'encodage de la console Windows. Les installeurs Windows et macOS
  sont produits par la même CI.
- **Pas de serveur HTTP local** : les routes de `gui.py` deviennent des commandes
  Tauri, et les images passent par un protocole interne. Il n'y a plus de port
  ouvert ni de jeton de session.
- **Performance et mémoire** : chaque effet est calculé en une seule passe par
  pixel, sans les copies intermédiaires de NumPy. Le traitement se fait par
  tuiles, donc la mémoire reste bornée. C'est indispensable sur iPad.
- **iPad** : Tauri 2 compile pour iOS, LibRaw se compile pour iOS, et le cœur
  Rust est le même partout.

## 2. Prototype réalisé : `rust/kora-core`

Il porte l'étape la plus coûteuse du rendu, `apply_official` : linéaire sRGB →
F-Gamut → F-Log2 → LUT officielle 65³ (trilinéaire) → gamma 2,2 → sRGB. Le calcul
est fusionné en une passe et parallélisé avec `rayon`.

```sh
cargo build --release --manifest-path rust/Cargo.toml
cargo test --release --manifest-path rust/Cargo.toml
.venv/bin/python scripts/compare_rust_core.py PHOTO.RAF PHOTO.DNG --film provia
```

Résultats sur de vrais RAW (meilleur temps sur 3 essais, même entrée décodée par KŌRA) :

| Fichier | Film | Python (10 threads) | Rust (14 threads) | Gain | Écart max (/255) | Pixels 8 bits différents |
|---|---|---|---|---|---|---|
| X-Trans RAF 26 Mpx | PROVIA | 0,403 s | 0,112 s | 3,6× | 0,00017 | 0,002 % |
| Leica DNG 60 Mpx | PROVIA | 0,831 s | 0,241 s | 3,5× | 0,00014 | 0,001 % |
| X-Trans RAF 26 Mpx | CLASSIC CHROME | 0,416 s | 0,111 s | 3,7× | 0,00012 | 0,001 % |
| Leica DNG 60 Mpx | CLASSIC CHROME | 0,827 s | 0,239 s | 3,5× | 0,00011 | 0,001 % |

Le rendu est **identique en pratique** : l'écart maximal vaut un dix-millième de
niveau 8 bits, et seuls de rares pixels tombent de l'autre côté d'un arrondi. Le
gain de 3,5× porte sur une étape que le code Python parallélisait déjà
bien. Les étapes moins optimisées en Python (courbes de tons, grain, flous)
devraient gagner davantage, mais ce n'est pas encore mesuré.

## 3. Mesures de l'application actuelle

| Étape | RAF X-Trans 26 Mpx | DNG Leica 60 Mpx |
|---|---|---|
| Ouverture d'une photo (`inspect`) | 2,3 s | 3,0 s |
| Décodage complet (LibRaw + conversion) | **8,1 s** | 5,5 s |
| Aperçu écran 3200 px, recette lourde, par réglage | 1,2 s | 1,3 s |
| Tuile 512 px à 100 % | 0,65 s | 0,94 s |
| Export JPEG, recette lourde | 3,5 s | 7,2 s |
| Mémoire maximale (RSS) | 3,3 Go | **6,5 Go** |

« Recette lourde » : Highlights −40, Shadows +30, Clarity +2, grain faible,
Color Chrome fort, Sharpness +1, Highlight Tone +1.

Répartition du rendu complet d'export (recette lourde, DNG 60 Mpx, 6,75 s) :
LUT officielle 1,69 s · détail sélectif des ombres 1,34 s · courbe de tons
linéaire 0,83 s · ton Fuji 0,59 s · grand flou (Clarity) 0,49 s · grain 0,46 s ·
préservation de teinte 0,39 s · flous 0,31 s · Color Chrome 0,30 s · encodage 0,30 s.
Aucune étape ne domine : le coût vient de la dizaine de passes NumPy sur l'image
entière. C'est exactement ce qu'un noyau Rust fusionné supprime.

## 4. Optimisations repérées (valables même sans Rust)

Classées par impact sur ce que l'utilisateur ressent.

1. **Dématriçage X-Trans : 8 s sur un seul cœur.** Le rawpy installé est compilé
   **sans OpenMP** (`rawpy.flags['OPENMP'] == False`), donc LibRaw utilise un seul
   cœur. Pistes :
   - Markesteijn 1 passe (`demosaic_algorithm=PPG`) : 5,5 s au lieu de 8,0 s. Écart
     moyen 0,03/255 et p99,9 à 1,5/255 par rapport aux 3 passes. À valider
     visuellement.
   - Compiler LibRaw avec OpenMP : gain de plusieurs fois sur 14 cœurs.
   - En Rust : dématriçage X-Trans parallèle par tuiles. C'est le gain individuel
     le plus important du projet.

   **Fait en 0.2.44** : LibRaw compilé avec OpenMP et un patch d'ordonnancement
   (`packaging/libraw-xtrans-deterministic-openmp.patch`), pixels identiques au
   décodage mono-thread. Voir `LOADING_0.2.44.md`.
2. **Le premier aperçu développé attend le décodage complet.** L'interface ne
   demande que la qualité `display`, qui exige le RAW en pleine résolution.
   Résultat : environ 10 s après l'ouverture d'un RAF (2,3 s d'inspection + 8,1 s
   de décodage), sauf si le préchargement a déjà fait le travail. La qualité
   `interactive` (demi-taille, 0,1 à 0,6 s) existe côté serveur mais n'est plus
   utilisée. Afficher d'abord ce rendu rapide, puis le remplacer par `display`,
   rendrait l'ouverture quasi immédiate. **Non retenu** : la 0.2.37 a retiré ce
   petit aperçu volontairement (voir `DISPLAY_0.2.37.md`). Le vrai remède est
   un dématriçage plus rapide (point 1).
3. **Ouverture d'un RAF : 1,2 s sur 2,3 s passées à générer le grain.** Quand la
   recette de l'appareil contient du grain, l'ajustement d'exposition
   (`estimate_reference_ev`) le calcule sur une vignette de 256 px. Mais
   `_grain_rows` génère et filtre le bruit sur tout le cadre de référence de
   6000 px. Il faudrait soit l'exclure de l'ajustement d'exposition (il est de
   moyenne nulle), soit le synthétiser directement à l'échelle réduite. À valider
   sur le corpus d'exposition.
4. **Chaque réglage recalcule la réduction plein format → écran** :
   `display_preview` redimensionne tout le RAW linéaire (0,21 s sur 60 Mpx)
   avant chaque rendu. Mettre en cache la version réduite par
   (photo, taille, optique) supprime ce coût à chaque mouvement de curseur.
   **Fait en 0.2.43** (`display_linear`), avant la fusion de ce travail ; ma version
   équivalente a été retirée au profit de celle-ci.
5. **Les rendus abandonnés continuent de calculer.** Quand le navigateur annule
   une requête, le thread Python va jusqu'au bout. Les tuiles ont un
   numéro de génération, mais pas l'aperçu `display`. Avec un curseur qu'on fait
   glisser, plusieurs rendus de plus d'une seconde peuvent donc se chevaucher.
   **Fait en 0.2.44** (voir `LOADING_0.2.44.md`).
6. **Mémoire : 6,5 Go en pointe pour un DNG de 60 Mpx.** Le cache de RAW
   linéaires peut atteindre 3 Go, plus les copies du rendu. C'est le principal
   risque sur les portables Windows à 8 ou 16 Go, et c'est rédhibitoire sur iPad.
   Un pipeline par tuiles est la vraie réponse.
7. **ExifTool lancé 3 à 4 fois par photo** (environ 60 ms à chaque fois).
   C'est mineur : un cache par (chemin, taille, date) ou `-stay_open` suffit. Sur
   iPad, ExifTool (Perl) n'existe pas, donc il faudra un lecteur de MakerNotes
   Fuji natif pour la quarantaine de balises utilisées.
8. **Paquet macOS** : Tcl/Tk (inutilisé) et SciPy entier sont embarqués. On peut
   gagner quelques Mo en les excluant dans `packaging/KoraMacOS.spec`. Gain
   faible ; Rust règle la question.

Les points 1, 4 et 5 sont faits, avec des pixels identiques bit à bit. Le point 3
modifie légèrement l'exposition estimée, et ne coûte qu'à la première photo de
chaque géométrie d'appareil dans une session (le champ de grain est ensuite en
cache). Il reste donc à valider. Le point 6 (mémoire) est le plus gros chantier
restant, et celui que la migration Rust par tuiles réglerait.

## 5. Architecture cible

```
kora/                        (Python : recherche, calibration, scripts d'audit)
rust/
  kora-core/    pipeline couleur, effets, recettes (serde), noyaux fusionnés
  kora-raw/     LibRaw via FFI (bindgen), dématriçage parallèle, MakerNotes Fuji
  kora-optics/  modèles Lensfun (distorsion, vignetage) lus depuis la base XML
  kora-io/      JPEG / TIFF 8-16 bits, ICC (lcms2), ZIP d'export
  kora-app/     application Tauri 2 ; reprend kora/static/* presque tel quel
```

- **Lecture RAW** : on garde LibRaw (via FFI) pour conserver exactement la
  compatibilité actuelle (RAF, DNG, CR3, NEF, ARW…). `rawler` (projet dnglab)
  reste une option pure Rust à évaluer plus tard.
- **Interface** : les appels `fetch('/api/…')` de `app.js` deviennent des
  `invoke(...)` Tauri. Les images passent par un protocole personnalisé.
- **Plus tard** : aperçu interactif sur GPU avec `wgpu` (Metal sur Mac et iPad,
  Direct3D 12 sur Windows).

## 6. Plan par étapes

Chaque étape a un critère de validation. Une étape ne commence que si la
précédente reproduit le rendu Python.

| Étape | Contenu | Critère de fin |
|---|---|---|
| 0 ✅ | Prototype `kora-core` : LUT officielle | Écart < 0,001/255, gain mesuré |
| 1 | Corpus de référence : N RAW × M recettes rendus par Python (`.npy` + JPEG) | Script reproductible, inclus dans la CI |
| 2 | Port de `render()` effet par effet (courbes, ton Fuji, Chrome, grain, flous, Clarity, N&B) | Écart max ≤ 1/255 sur tout le corpus |
| 2b | (optionnel) Exposer `kora-core` à Python avec PyO3 et l'activer dans l'app actuelle | Les utilisateurs profitent du gain avant la fin de la migration |
| 3 | Décodage : FFI LibRaw, récupération des hautes lumières, profils d'entrée, ajustement d'exposition | Même RAW linéaire que `decode()` |
| 4 | Application Tauri 2 : routes → commandes, cache, export, installation des LUT | Fonctions identiques à 0.2.41 sur Windows et macOS |
| 5 | CI de release (macOS ARM/Intel, Windows x64), signature, notarisation ; retrait de Python du paquet | Installeurs < 40 Mo, démarrage < 1 s |
| 6 | iPad : cible iOS de Tauri, sélecteur de documents, pipeline par tuiles, MakerNotes sans ExifTool | Export d'un RAF 40 Mpx sous 4 Go de RAM |

Ordre de grandeur : le code Python de l'application (sans l'atelier de recherche
firmware) fait environ 180 Ko. Les étapes 1 à 5 représentent **plusieurs mois à
temps partiel**. Le plus long n'est pas d'écrire le code, c'est de prouver que
chaque effet produit la même image.

## 7. Ce qui reste en Python

L'atelier de recherche natif (`emulation`, `dma`, `messaging`, `threadx`…), les
scripts de calibration et d'audit (`scripts/`), et la génération du corpus de
référence. Ils ne sont pas livrés aux utilisateurs, et Python y est plus
productif.
