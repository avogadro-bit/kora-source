# Ressources tierces et provenance

Le code du projet ne confère aucun droit sur les marques Fujifilm, les LUT, les firmwares ou les dépendances tierces. Ce projet indépendant n’est pas affilié à Fujifilm.

## LUT Fujifilm

Source : [page officielle des LUT](https://www.fujifilm-x.com/global/support/download/lut/), archive GFX ETERNA 55 v1.10. La page décrit leur chargement dans un logiciel de montage ; ce projet ne présume pas d’un droit de redistribution et exclut les `.cube` de Git, du wheel et de l’archive source.

Le manifeste du projet contient uniquement leurs noms et SHA-256. L’utilisateur télécharge l’archive séparément, consulte les conditions du fournisseur puis l’installe localement avec `python -m kora.lut_install`. L’installateur conserve les octets originaux.

## Recherche native et balance des blancs

Les firmwares, modules extraits, outils tiers téléchargés et rapports de recherche restent locaux dans `research/`, exclu de Git. Le code du banc décrit des observations et des adresses, mais n’inclut pas les binaires du fabricant.

`kora/luts/wb-shifts-xt4.json` contient 38 coefficients numériques de balance des blancs observés dans la configuration du X-T4 2.12. Leur provenance et les limites de l’application RGB sont conservées dans le fichier. Ce sont des données dérivées d’une analyse du firmware, pas une calibration indépendante du X100VI. La licence choisie pour le code original ne s’étend pas automatiquement à des éléments tiers ; cette provenance doit rester visible lors du partage.

## Dépendances

La release macOS intègre Python, rawpy/LibRaw, NumPy, SciPy, Pillow, Pydantic, tifffile et lensfunpy/Lensfun. Leurs licences et notices sont incluses dans `Contents/Resources/Third-Party-Notices` et dans une archive jointe à la release publique. Les sources correspondantes des bibliothèques natives concernées et leurs scripts de compilation sont disponibles dans `Dependency-Sources.zip`. Voir [les notices de distribution](docs/DEPENDENCY_NOTICES.md). Unicorn et Capstone ne sont pas intégrés à l’application. ExifTool reste externe sur macOS et est inclus dans l’app Windows (voir ci-dessous). Les LUT officielles, firmwares, photos personnelles et profils ICC propriétaires ne sont pas redistribués.

### Décodeur RAW multi-cœur et ExifTool

À partir de 0.2.44, les apps macOS Apple Silicon et Windows x64 embarquent
rawpy 0.27.1 compilé par ce projet (`0.27.1+kora.xtrans1`), avec OpenMP et une
modification de LibRaw : `packaging/libraw-xtrans-deterministic-openmp.patch`
ordonne les tuiles du dématriçage X-Trans parallèle et la copie demi-taille
des données brutes pour reproduire exactement le résultat mono-thread. Conformément à la LGPL 2.1 de LibRaw, ce patch est
joint aux notices et à `Dependency-Sources.zip`, avec les sources LibRaw
d'origine ; `scripts/build_rawpy_openmp.py` et `scripts/build_rawpy_windows.py`
reconstruisent la bibliothèque. Sur macOS, le runtime OpenMP de LLVM 22.1.8
(Apache-2.0 avec exception LLVM) est inclus avec sa licence. Sous Windows, le
runtime OpenMP `vcomp140.dll` est le composant redistribuable de Microsoft
Visual C++, déjà fourni par la wheel rawpy officielle.

L'app Windows embarque aussi ExifTool 13.59 pour Windows 64 bits, de Phil
Harvey (même licence que Perl : Artistic License ou GPL), avec la distribution
Strawberry Perl qui l'accompagne. Ses licences sont conservées dans
`tools/exiftool_files/LICENSE` et `tools/exiftool_files/Licenses_Strawberry_Perl.zip`.
Seul le lanceur `tools/exiftool.exe` (`exiftool(-k).exe` d'Oliver Betz, sous
licence CC0) est modifié : `scripts/windows_manifest.py` remplace son manifeste
d'application par un manifeste qui garde `longPathAware` et ajoute
`activeCodePage` UTF-8. Sans cela, il ne trouve pas Perl quand le dossier de
l'app contient des caractères absents de la page de code Windows, comme « KŌRA ».
Les fichiers d'`exiftool_files` sont inchangés.
Sur macOS, ExifTool reste une installation externe facultative.

## Code original

La release embarque lensfunpy et la bibliothèque Lensfun sous LGPL 3.0. À partir
de 0.2.35, `kora/lensfun_db/` contient une copie sans modification des fichiers
XML de la [base officielle Lensfun, format 1](https://lensfun.github.io/db/),
sous **CC BY-SA 3.0**, avec attribution au projet Lensfun et à ses contributeurs.
La licence complète et le manifeste `origin.json` (date et SHA-256 de l'archive)
accompagnent les données dans le dépôt, le wheel, l'archive source et les apps.
Les commentaires XML conservent les attributions individuelles présentes.
Cette base remplace à l'exécution celle, plus ancienne, livrée avec lensfunpy.
Les modèles ACM, réservés au format 2, ne sont pas dans cette base compatible.
Les coefficients DNG Leica sont lus à la demande dans les photos de l’utilisateur.
L’implémentation géométrique se réfère à la [spécification DNG Adobe](https://helpx.adobe.com/camera-raw/digital-negative.html)
et l’intégration des profils à la [documentation lensfunpy](https://letmaik.github.io/lensfunpy/).

Le code original est distribué sous [licence MIT](LICENSE). Cette licence ne remplace pas celles des ressources tierces. Ce document fournit l’inventaire des ressources ; il ne constitue pas une validation juridique des droits de distribution.

## Experimental Kodachrome 64 model

The generated scientific tables in `kora/film_data` are adaptations of CIE
1931 observer and D65/D50 data (CC BY-SA 4.0). The attribution, dataset DOIs,
license link and scope of the adaptations are in `kora/film_data/NOTICE.txt`.
Their CC BY-SA terms are separate from the MIT license on Kora's code.
Digitized Kodak E-88 plots remain attributed to Eastman Kodak Company; they
are reconstructed drawings, not an original numerical Kodak dataset.
Status A weights from python-colormath are BSD-3-Clause; the license is included.
Reconstruction code, source tables and metadata are provided in the source
archive under `scripts/kodachrome_reference`. No photograph or Fuji LUT enters
these generated tables. See `docs/KODACHROME64.md` for method and limitations.
