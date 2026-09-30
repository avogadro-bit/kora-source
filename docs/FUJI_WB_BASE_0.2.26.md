# Fuji WB base — 0.2.26

The old decoder used LibRaw camera white balance, which includes the recorded
Fuji R/B fine-tuning, while KŌRA displayed zero R/B offsets. On the X-M5 sample
DSCF5367, the recorded shift is Red +80 / Blue -100 in MakerNotes (R +4 / B −5
in the camera menu). As-shot multipliers are R=649, G=302, B=443; the separate
Auto estimate is R=573, G=302, B=533. These are different starting points.

For RAF files in ordinary Auto WB with a valid recorded shift and a valid
separate Auto coefficient tag, KŌRA now passes the unshifted coefficients to
LibRaw as explicit sensor-space user white balance. The illuminant estimate is
preserved; only the recipe fine-tuning is removed. Preview and full decode use
the same coefficients. No inverse colour adjustment is applied to display RGB.

Supported coefficient layouts are WB_GRBLevelsAuto (G,R,B) and
WB_GRGBLevelsAuto (G,R,G,B). Invalid or unavailable data, custom/Kelvin/preset
WB, and Auto white/ambience priority are not guessed: they retain as-shot WB
and the source label explicitly says that the shift was not removed. Zero
recorded shifts and other RAW formats retain their existing behavior.

Exposure matching uses a separate as-shot decode when WB neutralization is
active. Thus the tinted embedded JPEG cannot make exposure fitting compensate
for the newly neutralized colour. That JPEG is also not briefly displayed as
the initial main preview for these files; camera thumbnails remain thumbnails.

Default KŌRA R/B settings stay at zero. Explicit Shooting Settings restores the
recorded R/B settings only if they were removed during decode. This recipe
application still uses KŌRA's independent RGB adaptation, so it does not promise
pixel-identical native Fuji output. The WB menu calls the base Camera rather
than As Shot, and source details report the correction policy and coefficients.

Validation includes coefficient order, strict units/ranges, unsupported-mode
fallback, no guessed correction, both decoder sizes, exposure-anchor separation
and explicit shooting-setting restoration. Three local X-M5 RAF originals
(DSCF5367, DSCF5368, DSCF5370) are checked at full resolution. Source hashes are
compared before and after. Generated photographs are excluded from releases.

Recipe response revision is 18. Restart after installing. Existing recipes
applied to supported shifted RAFs now start from the neutralized base.

Sources: [ExifTool Fuji tag definitions](https://raw.githubusercontent.com/exiftool/exiftool/master/lib/Image/ExifTool/FujiFilm.pm)
(channel order and twenty fine-tune units per modern camera step), and
[LibRaw Fuji metadata reader](https://raw.githubusercontent.com/LibRaw/LibRaw/master/src/metadata/fuji.cpp)
(distinct as-shot and Auto coefficient tables). Coefficient values above are
read from the local test file, not inferred from a generic camera profile.
