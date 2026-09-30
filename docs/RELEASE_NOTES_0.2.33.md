# KŌRA 0.2.33 — macOS public beta

This release includes the improvements developed since the previous public
beta, 0.2.21.

## Display and zoom

- Fit view now progressively loads detail from the full-resolution RAW after
  the quick preview, at a resolution appropriate for the display.
- Zoom accounts for Retina density. At 100%, one developed image pixel maps
  to one physical screen pixel.
- Panning and zoom changes retain loaded detail and reuse cached regions.
- Fine coloured edges retain more detail in the preview transport.
- Without-film comparison receives the same detail refinement and keeps the
  selected crop and output geometry. Wait for **Image ready** to judge sharpness.

## RAW development and recipes

- Improved highlight recovery, colour stability, transitions to white, and
  control of RAW Highlights and Whites, including strong reductions.
- Separate Fuji-style Highlight Tone and Shadow Tone controls, informed by
  X-M5 reference measurements; existing RAW recovery controls remain available.
- Revised grain and X-M5 white-balance handling. Where supported metadata is
  available, the camera's R/B shift is removed from the starting white balance.
- Updated Classic Negative, PRO Neg. Hi, Nostalgic Negative, and Color Chrome
  adaptations, with film improvements available across supported RAW formats.
- A limited input-colour adjustment for Leica Q3 43 DNGs, based on paired
  reference photographs. This is not a universal Leica calibration.

## Downloads

- **Kora-0.2.33-macOS-arm64.dmg**: installer for Apple Silicon, macOS 14 or newer.
- **Kora-0.2.33-macOS-arm64.zip**: the same self-contained application in a ZIP.
- **kora-0.2.33.tar.gz** and **kora-0.2.33-py3-none-any.whl**: Python source
  distribution and package. GitHub also provides source archives for this tag.
- Dependency sources, third-party notices, and SHA-256 checksums are attached.

Open the DMG and drag KŌRA into Applications to replace the previous version.
The app is ad-hoc signed, not Apple-notarized. Official Fujifilm LUTs must be
installed separately through Setup; they are not included in these downloads.

## Validation and limits

255 Python tests and 12 JavaScript tests passed locally. The built macOS app
was checked with Leica DNG and X-M5 RAF files, including detailed preview,
without-film comparison, and full-resolution DNG rendering. Automated source
checks cover Linux, macOS, and Windows; this release provides macOS installers.

The first detailed development can take several seconds. Display transport is
8-bit sRGB JPEG; TIFF export retains its separate 8/16-bit options. The photo
engine remains an independent approximation, not the native Fuji engine or an
exact match to X RAW STUDIO or Capture One. See HISTORY.md and the linked
validation notes for the scope and remaining limits of each adjustment.
