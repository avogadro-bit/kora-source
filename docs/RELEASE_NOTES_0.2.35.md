# KŌRA 0.2.35 — macOS public beta

This release adds broader optical correction coverage and includes the
multi-camera RAW improvements developed in 0.2.34.

## Lens detection and optical corrections

- Bundles the official Lensfun database dated September 24, 2026: **1,569
  profiles and 1,057 camera references**, adding 265 profiles and 109 cameras
  compared with the previous bundled database.
- Recognizes more lenses from resolved EXIF identifiers and dedicated
  fixed-lens camera profiles, including the X-M5 XC15–45 mm, Canon R5 with
  Sigma 50 mm Art, and Nikon P1000 in the tested RAW set.
- Shows the detected lens and offers **Apply available corrections** when a
  reliable profile exists. The button enables available distortion and
  vignetting corrections, with Undo support.
- Uses the same profiles for previews, zoom details, and exports. Loading a
  photo preserves its existing recipe. Ambiguous or missing profiles are
  left without automatic correction.

## Multi-camera RAW improvements

- Reduces magenta colour contamination in saturated highlights for the
  generic Bayer RAW input, using sensor saturation and white-balance data.
- Raises the import limit to **512 MiB**, including large Hasselblad RAW files.
- Gives a clear unsupported-compression message for Nikon HE/HE* files.
- Adds a reproducible compatibility test harness and a public sample index;
  test photographs are not included in the source or release.

## Downloads

- **Kora-0.2.35-macOS-arm64.dmg**: Apple Silicon installer, macOS 14 or newer.
- **Kora-0.2.35-macOS-arm64.zip**: the same self-contained application in a ZIP.
- **kora-0.2.35.tar.gz** and **kora-0.2.35-py3-none-any.whl**: Python source
  distribution and package. GitHub also provides source archives for this tag.
- Dependency sources, third-party notices, and SHA-256 checksums are attached.

Open the DMG and drag KŌRA into Applications to replace the previous version.
The app is ad-hoc signed, not Apple-notarized. Official Fujifilm LUTs are
installed separately through Setup and are not included in these downloads.

## Validation and limits

**265 Python tests and 15 JavaScript tests passed locally.** The built 0.2.35
macOS app passed 300 checks on 12 real RAW files, including optical corrections,
12 film simulations, zoom details, full-resolution JPEG and 16-bit TIFF export.
The preceding multi-camera campaign covered 21 RAW files from Sony, Nikon,
Canon, Hasselblad and Fujifilm: 19 decoded successfully; the two Nikon HE/HE*
samples remain unsupported. Automated source checks cover Linux, macOS and
Windows; this release provides macOS installers.

Profile counts do not imply every lens has every correction at every focal
length. The tested Hasselblad XCD 21/38V and Fujifilm GF63 mm remain without a
calibrated profile; ambiguous lens identifiers are not guessed. Chromatic
aberration correction is not added by this release. Vignetting retains the
existing distant-focus assumption. See [optical coverage and validation](OPTICS_0.2.35.md)
and the [multi-camera test report](MULTICAMERA_0.2.34.md).

The photo engine remains an independent approximation, not the native Fuji
engine or an exact match to X RAW STUDIO or Capture One.
