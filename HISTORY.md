# Historique de recherche (états et nombres de tests datés)

Ces notes décrivent les étapes antérieures ; suivre README.md pour installer la version actuelle.

## 0.2.33 — Affichage détaillé en vue entière et sur Retina

La vue entière charge désormais les détails du RAW après le premier aperçu,
avec une résolution adaptée à la densité de l'écran. Le zoom à 100 % correspond
à un pixel de photo par pixel physique. Les détails déjà disponibles restent
visibles pendant les déplacements et les changements de zoom ; les régions
en cache sont réutilisées. Même qualité pour la comparaison sans film, avec
conservation du cadrage. [Vérifications et limites](docs/DISPLAY_0.2.33.md).

## 0.2.32 — Transitions et contraste des hautes lumières

Correction des donneurs de couleur partiellement saturés dans les DNG Leica,
transition plus progressive vers le blanc et courbe RAW qui conserve davantage
de contraste aux minima Highlights/Whites. Cas reproduits sur L1007741 et
L1003382, en PROVIA et Classic Negative. Les références d'exposition RAF et
les deux commandes de tonalité Fuji de 0.2.31 sont préservées.
[Détails et limites](docs/HIGHLIGHTS_0.2.32.md).

## 0.2.31 — Commandes Highlight Tone et Shadow Tone

Ajout des deux commandes Fuji de −2 à +4 par demi-pas, avec une réponse
mesurée sur 50 variantes X-M5 Classic Negative / DR100. L'écart moyen de
réponse diminue de 43 % sur trois scènes réservées au contrôle. Les quatre
corrections RAW restent séparées et les anciennes recettes sont préservées.
Cette amélioration ne constitue pas une équivalence au moteur natif Fuji.
[Méthode, résultats et limites](docs/FUJI_TONE_0.2.31.md).

## 0.2.30 — Ajustement d'entrée Leica Q3 43

Petite correction du biais bleuté en entrée, dérivée de la façade commune de
L1007724.DNG et DSCF5367.RAF, avec contrôle sur les exports natifs X-M5.
L'exposition différente des deux prises de vue n'est pas intégrée au profil.
Portée limitée aux DNG du Q3 43 ; contrôle de stabilité sur quatre autres DNG.
Noms des films simplifiés dans le menu, provenance conservée dans la description.
[Méthode, mesures et limites](docs/LEICA_PAIR_0.2.30.md).

## 0.2.29 — Adaptations photo communes aux RAW multimarques

Classic Negative, PRO Neg. Hi, Nostalgic Negative et la force ajustée de Color
Chrome s'appliquent désormais à tous les RAW pris en charge, après conversion
dans l'espace de travail commun. Les films sont disponibles dans le menu sans
restriction X-M5. Le grain et les réglages Highlights/Whites étaient déjà communs.
Les coefficients WB propres au X-M5 restent limités à ce modèle.
[Portée et vérifications](docs/MULTIRAW_FILMS_0.2.29.md).

## 0.2.28 — Classic Negative pour les RAF X-M5

Correction chromatique mesurée sur les références X-M5, en conservant la
luminosité et les gris du rendu précédent. Les cinq rendus de départ se
rapprochent des JPEG du boîtier ; 245 variantes ont été comparées, avec un gain
moyen mais des limites persistantes sur certains ciels et réglages poussés.
[Mesures et limites](docs/CLASSIC_NEGATIVE_0.2.28.md).

## 0.2.27 — Corrections vérifiées avec le X-M5

395 variantes exportées par X RAW STUDIO et le X-M5, sur cinq scènes : grain
plus proche des références, WB Auto et préréglages appliqués dans l'espace du
capteur, décalage R/B corrigé, Color Chrome moins excessif sur X-M5. Adaptations
PRO Neg. Hi et Nostalgic Neg. disponibles pour les RAF X-M5, validées sur trois
scènes distinctes de celles utilisées pour l'ajustement. Correction des libellés
ASTIA/PROVIA/Velvia à l'import. Le moteur reste une approximation ; toutes les
simulations et commandes ne sont pas équivalentes au boîtier.
[Détails, mesures et limites](docs/XM5_CALIBRATION.md).

## 0.2.26 — Base WB neutre pour les RAF Fuji Auto compatibles

Les décalages R/B du boîtier ne sont plus inclus dans le point de départ lorsque
le RAF fournit les coefficients Auto sans décalage. Correction vérifiée sur les
RAF X-M5, avec exposition de référence séparée et signalement des cas non pris
en charge. [Détails](docs/FUJI_WB_BASE_0.2.26.md).

## 0.2.25 — Réglages Highlights et Whites plus précis

Whites conserve son action après une forte baisse des Highlights. Réponse plus
progressive près de zéro, réduction étendue en fin de course et conservation
bornée des détails avant la simulation de film. Saisie au dixième dans le GUI.
[Détails et limites](docs/HIGHLIGHTS_AND_WHITES_0.2.25.md).

## 0.2.24 — Correction des couleurs dans les hautes lumières

Suppression des plaques cyan/magenta introduites en 0.2.22 et conservées en
0.2.23 sur les grandes zones partiellement saturées. Estimation progressive
à partir de couleurs non saturées, sans frontières de proximité, et transition
continue lorsque le dernier canal sature. Grain inchangé.
[Détails et validation](docs/HIGHLIGHT_REGRESSION_0.2.24.md).

## 0.2.23 — Grain inspiré des références Fuji

Texture plus fine, échelle photographique stable, intégration des aperçus et
continuité du grain au zoom. [Détails et limites](docs/GRAIN_0.2.23.md).

## 2026-09-16 — KŌRA 0.2.0 macOS application

- Added a self-contained macOS `.app`, ZIP, and DMG release build.
- The packaged application opens its authenticated local session automatically;
  Python and the project virtual environment are no longer required by users.
- Kept the official LUTs outside the release. First-run Setup downloads from
  Fujifilm or accepts an existing downloaded ZIP, verifies all ten tables, and
  installs them in the user data directory.
- Added startup crash logging under `~/Library/Logs/KŌRA/app.log`.

## 2026-09-15 — GUI setup and grain/DR preview revision 11

- Added a first-run GUI setup dialog that downloads the official GFX ETERNA 55
  archive from Fujifilm and installs only user-selected, hash-verified LUTs.
- Replaced the low-pass Gaussian grain with deterministic monochrome band-pass
  texture. Roughness now controls amplitude independently from grain size.
- Fixed signed negative working-space values being inverted to white by
  DR200/DR400 in reduced DNG previews.

# Studio RAW multimarque — LUT officielles Fujifilm

Révision 10 : [entrée RAW commune, profils par modèle et import multimarque](docs/MULTICAMERA_INPUT_V10.md). CR3, RW2 et IIQ testés sur les fichiers locaux, en plus des DNG et RAF.

Révision 9 : [audit Classic Negative / Leica, gamma officiel 2,2 et normalisation Q3 43 recalculée](docs/CLASSIC_NEGATIVE_LEICA_V9.md). Amélioration mesurée, caractère photographique Leica encore à valider.

Révision 8 (historique) : [entrée Leica Q3 43, luminosité fixe et conversion couleur flottante](docs/LEICA_INPUT_V8.md). Les autres modèles et les RAF conservent leur traitement précédent.

Révision 7 : [correction de l'exposition initiale des RAF à partir de leur recette source](docs/RECIPE_EXPOSURE_V7.md). Amélioration mesurée, fidélité Fuji encore incomplète.

Audit actuel : [comparaison des RAF/JPEG X100VI et résultats](docs/PAIRED_FUJI_VALIDATION.md).
Les essais de calibration n’ont pas passé les critères ; ils ne sont pas appliqués aux DNG.

Recherche complémentaire : [23 références publiques, mesures des tonalités et contrôle FX Blue](docs/ONLINE_REFERENCE_AUDIT.md). Les nouvelles courbes restent expérimentales et ne modifient pas le GUI.


Depuis le changement de direction autorisé par l’utilisateur, le GUI développe réellement les RAF et DNG avec un moteur indépendant. **Classic Negative et neuf autres films utilisent désormais les LUT officielles du GFX ETERNA 55. L’adaptation photo reste non calibrée contre les JPEG Fuji.** Les recettes modifient l’aperçu et peuvent être exportées en JPEG ou TIFF 8/16 bits.

Lancer `Launch Kora.command`, puis ouvrir le lien de session affiché. Le nouveau studio utilise le port **8766** ; un ancien serveur de recherche sur 8765 peut encore être ouvert. Les fichiers iCloud non téléchargés ne sont pas lus.

[Audit des paramètres et corrections](docs/PARAMETER_AUDIT.md) · [LUT officielles : pipeline et validation](docs/OFFICIAL_LUT_STUDIO.md) · [Utilisation et couverture des options](docs/GUI.md) · [Architecture et validation du rendu](docs/INDEPENDENT_STUDIO.md).

Le moteur natif de recherche reste séparé et indisponible. Les sections historiques ci-dessous décrivent ce banc natif, pas le moteur indépendant du GUI.

---

# KŌRA

Projet de recherche pour un équivalent de **FUJIFILM X RAW STUDIO sans boîtier**, avec prise en charge RAF et DNG et exécution du **véritable traitement Fuji**.

**État : interface locale RAF/DNG disponible pour les aperçus et les recettes JSON. Premières fonctions du firmware X-T4 2.12 exécutées sur Mac. Le calcul natif des pixels et l’application des recettes à l’image restent à construire.**

Les trois étapes de réglages terminent dans **272 essais réussis**, avec calendrier natif. La synchronisation passe 24 cas. L’orchestrateur RAW termine l’envoi de son message ; la tâche destinataire le reçoit et transmet ses notifications vers la tâche 7. **Cela ne valide pas encore le traitement des pixels.** [Résultats de la messagerie](docs/NATIVE_MESSAGES.md).

La commande `render` refuse explicitement de produire un résultat tant que la chaîne native n’est pas reconstruite. Aucun filtre approximatif n’est utilisé. Les aperçus LibRaw et les JPEG embarqués servent uniquement aux diagnostics et sont identifiés séparément.

Les coefficients WB et le bloc DEFAULT du DAT sont retrouvés ; le gestionnaire natif de balance des blancs termine. Avec la préparation partielle du programme RAW 6, le firmware réserve la ressource intermédiaire `0x2f`. La construction native des listes DMA passe **52 essais**. Le mode de buffers 7 a aussi été testé : sa capacité de 55,5 Mo reste inférieure aux 81,9 Mo requis par la géométrie X100VI actuelle du banc. [Résultats](docs/NATIVE_DMA.md).

Les conditions de lancement et de statut DMA passent **84 essais sur registres synthétiques statiques**. Le callback natif et les attentes sont vérifiés séparément, avec conservation ou effacement de la notification. L’attribut réel de la tâche dépend encore d’un mot de pile non reconstruit. **68 tests unitaires passent ; aucun rendu natif RAF/DNG n’est encore disponible.** [Portée exacte et dépendances](docs/NATIVE_DMA_CONTROL.md).

Le gestionnaire mémoire Fuji crée maintenant les allocations de la file, du pool de messages et de la pile RAW dans une arène de banc. Les paramètres de tâche sont lus par l’appelant natif dans la ROM. Ce parcours confirme que le champ de notification dépend d’un état de pile antérieur encore inconnu ; la création de tâche ne termine pas encore.

La préparation précédente du coordinateur est maintenant exécutée également : six initialisations natives, puis la création RAW, jusqu’à 3 399 instructions. Le champ inconnu n’est pas écrit dans ce parcours ; sa provenance remonte aux étapes de démarrage et de création des tâches antérieures, encore à reconstruire.

Un parcours indépendant depuis la première création du démarrage confirme la même dépendance dès la tâche 26, après 2 534 instructions. Ses allocations réussissent, mais son attribut reste inconnu. La prochaine dépendance est donc la provenance de la pile avant cette séquence, et non seulement la préparation propre à RAW.

La tâche qui appelle le module image est maintenant identifiée : **tâche 86, pile de 4 Kio remplie nativement avec l’octet `0x56`**. Son entrée isolée sélectionne le gestionnaire de démarrage puis s’arrête sur un verrou global non initialisé. Le contexte noyau et le démarrage complet restent à reconstruire. [Détail et limites](docs/NATIVE_BOOT_TASK.md).

Les initialisations préalables de ce verrou sont désormais exécutées séparément. Elles atteignent une lecture matérielle inconnue à `0xff70f03c` après 45 656 instructions dans l’initialiseur final. Les états interrompus ne sont pas réutilisés. **La reproduction exacte reste bloquée par des dépendances matérielles non modélisées et non validées ; les tests de diagnostic ne valident aucun rendu d’image.**

## Livrables

- Interface photo locale : bibliothèque RAF/DNG, recherche, aperçu intégré, zoom, réglages de recette, brouillons et import/export JSON.
- Inventaire RAW avec détection des fichiers iCloud non téléchargés et des fichiers annexes.
- Inspection CFA, niveaux noirs/blancs, balance des blancs, matrices couleur et réglages Fuji.
- Préparation de petits jeux d’essai : tableau float32 linéaire sRGB, aperçu neutre, référence embarquée et provenance SHA-256.
- Inspection statique X6/X8 et extraction validée du DAT X-T4 2.12 : sept sommes de contrôle, quatre objets décompressés, manifestes SHA-256.
- Cartographie corroborée de deux modules ARM du X-T4 et probes natifs : identifiants de films, construction des paramètres RAW et fautes sur entrées invalides.
- Module système non compressé identifié ; circulation native des paramètres, traces mémoire, gardes des plages initialisées et essais ciblés ThreadX.
- Calendrier, construction d’objets de synchronisation et initialisation des requêtes exécutés nativement ; lecture native des métadonnées d’un RAF réel.
- Banc Unicorn ARM, Thumb et ARM64 : régions explicites, registres, traces, erreurs mémoire, sorties et limites d’exécution.
- Comparaison stricte de pixels JPEG/PNG/TIFF/NPY, conservant les TIFF 16 bits.
- Schéma de recette JSON, séparé des codes internes à rétro-ingénier.

Voir [les résultats natifs et leur reproduction](docs/NATIVE_XT4.md), [l’étude de faisabilité](docs/RESEARCH.md) et [la validation locale](docs/VALIDATION.md).

## Utilisation sur ce Mac

Double-cliquer sur [Launch Kora.command](Launch%20Kora.command), puis ouvrir le lien affiché dans le terminal. Le lanceur utilise les deux dossiers photo fournis. Un seul service peut utiliser le port 8765 à la fois ; laisser sa fenêtre Terminal ouverte pendant l’utilisation.

Ou lancer l’interface manuellement :

```bash
cd /chemin/kora
.venv/bin/python -m kora gui \
  --root '/chemin/Photos' \
  --root '/chemin/Photos/Fuji'
```

Le service fonctionne sur `127.0.0.1`, avec un lien de session affiché à chaque lancement. Il ne nécessite ni boîtier ni service distant. Les fichiers non téléchargés restent signalés iCloud. [Guide de l’interface et limites actuelles](docs/GUI.md).

Dans le terminal :

```bash
cd /chemin/kora
.venv/bin/python -m kora status
.venv/bin/python -m kora --help
.venv/bin/python -m unittest discover -s tests -v
```

L’environnement local réutilise les bibliothèques de Miniconda et contient Unicorn/Capstone. Sur une autre machine, créer un environnement Python 3.11+ et installer `pip install -e '.[emulation]'`. ExifTool est nécessaire pour les métadonnées détaillées.

Dans le bac à sable Codex de ce Mac, les commandes Unicorn ont produit SIGILL ; elles ont passé les tests hors bac à sable après autorisation. Depuis un terminal macOS ordinaire, utiliser les commandes ci-dessus.

```bash
# Inventaire : ne déclenche pas le téléchargement des originaux iCloud
.venv/bin/python -m kora inventory "/chemin/Photos" --output outputs/inventory.json

# Diagnostic d’un RAW local
.venv/bin/python -m kora probe "/chemin/photo.DNG"

# Préparer un jeu d’essai neutre ; le dossier destination doit être nouveau
.venv/bin/python -m kora prepare "/chemin/photo.RAF" outputs/sample

# Inspection du firmware déjà téléchargé localement
.venv/bin/python -m kora firmware-inspect research/firmware/XT4-2.12.DAT

# Extraction vers un dossier nouveau
.venv/bin/python -m kora firmware-extract research/firmware/XT4-2.12.DAT research/extracted/xt4-replay

# Code Fuji réel : noms internes, puis constructeur de paramètres (aucun calcul de pixels)
.venv/bin/python -m kora xt4-film-probe research/extracted/xt4-2.12/unpacked_00260000.bin
.venv/bin/python -m kora xt4-parameter-probe research/extracted/xt4-2.12
.venv/bin/python -m kora xt4-chain-probe research/extracted/xt4-2.12
.venv/bin/python -m kora xt4-threadx-probe research/extracted/xt4-2.12
.venv/bin/python -m kora xt4-runtime-probe research/extracted/xt4-2.12
.venv/bin/python -m kora xt4-sync-probe research/extracted/xt4-2.12
.venv/bin/python -m kora xt4-raw-frontier-probe research/extracted/xt4-2.12
.venv/bin/python -m kora xt4-raf-metadata-probe research/extracted/xt4-2.12 "/chemin/photo.RAF"
.venv/bin/python -m kora xt4-resource-probe research/extracted/xt4-2.12 "/chemin/photo.RAF"
.venv/bin/python -m kora xt4-message-probe research/extracted/xt4-2.12
.venv/bin/python -m kora xt4-resource-probe research/extracted/xt4-2.12 "/chemin/photo.RAF" --with-receiver

# Valider l’infrastructure d’émulation ; instructions synthétiques, pas du code Fuji
.venv/bin/python -m kora emulator-selftest

# Générer une recette puis la valider
.venv/bin/python -m kora recipe --output outputs/recipe.json
.venv/bin/python -m kora recipe outputs/recipe.json

# Comparaison exacte de deux sorties de même taille/type/profil/orientation
.venv/bin/python -m kora compare reference.tiff candidate.tiff
```

Les rapports existants ne sont pas écrasés : utiliser un nouveau nom pour les exécutions suivantes. Les photos sources ne sont jamais modifiées.

## Banc d’émulation

`emulate configuration.json` attend les champs `architecture` (`arm`, `thumb`, `arm64`), `entry`, `stop`, `regions`, et éventuellement `registers`, `outputs`, `instruction_limit`, `timeout_us`, `provenance`.

Chaque région possède `address`, `size` (multiples de 4096), `permissions` et au choix `file` (relatif à la configuration) ou `hex`. La mémoire non initialisée d’une région déclarée est mise à zéro et cette quantité apparaît dans le rapport. Les zones non déclarées provoquent une erreur ; aucune réponse de périphérique n’est inventée. `reached_stop` indique uniquement que l’adresse de fin a été atteinte.

Le banc générique ne charge pas directement un DAT. L’extracteur et les probes X-T4 ajoutent deux modules et des fonctions identifiées, avec des empreintes obligatoires. Le RTOS complet et les accélérateurs d’image restent à reconstruire. Les rapports gardent `image_pipeline_validated: false` même si une fonction atteint son adresse de fin.

Les nouveaux probes peuvent aussi charger l’extrait système de `main.bin`. `initialized_only` et `valid_ranges` gardent les octets inconnus interdits dans une page allouée ; `write_initializes` suit les octets initialisés par des écritures natives. `memory_trace` conserve des observations bornées. [Usage et limites](docs/NATIVE_RUNTIME.md).
# 0.2.22 — Recover partially clipped Leica highlights

Preserve surviving RAW colour and texture when both Bayer green sites saturate.
Remove the brightness-only return to white and let recovered colour through the
film shoulder. See [validation and limits](docs/HIGHLIGHT_RECOVERY_0.2.22.md).
