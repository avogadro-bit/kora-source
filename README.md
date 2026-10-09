# KŌRA

A local RAW studio that works without a connected camera. It develops photographs through an independent photo adapter and the official GFX ETERNA 55 LUTs, which must be installed separately. The interface is in English and starts with PROVIA / Standard.

**This project is neither a Fujifilm product nor an exact reproduction of the Fujifilm image engine.** The video LUTs are official; their adaptation to photographic RAW files and the recipe controls are independent and do not guarantee an X RAW STUDIO match. The separate native-engine research workbench does not produce images.

## macOS application

The GitHub release provides a self-contained **KŌRA.app** for Apple
Silicon Macs running macOS 14 or newer, in ZIP and DMG formats. It does not
require Python. Open the application and it launches the local studio in its own
full-screen macOS window. On first launch, **Setup** links to the
official Fujifilm download and lets the user choose the downloaded GFX ETERNA 55
ZIP. The ten LUTs are hash-verified and installed locally; they are not bundled or
redistributed by this project. See [macOS release and Gatekeeper notes](docs/MACOS_RELEASE.md).

## Experimental Kodachrome 64

Version 0.2.42 adds **Kodachrome 64 · Experimental** beside the Fuji films.
Select it in FILM SIMULATION and adjust Push / Pull. This built-in model comes
from the E-88 study; it is not a calibrated reproduction of film.
[Method, use and limits](docs/KODACHROME64.md).

## Performance and portability in 0.2.43

Preview adjustments reuse the reduced RAW buffer; batch exports retain only the
active workers' JPEGs in memory. Metadata requests share a small invalidated cache,
and Windows metadata reads support Unicode file paths without opening a console.
On one 60 MP DNG, repeated 1800-pixel Kodachrome previews took a median 124 ms
instead of 276 ms, with identical decoded JPEG pixels. Initial RAW decoding is
unchanged. Reproduce this comparison with `scripts/benchmark_preview.py`.

Separate macOS arm64/x86_64 builds and Windows x64 builds now audit native
dependencies and packaged assets before creating installers. See
[platform targets and validation limits](docs/PORTABILITY.md); configured CI jobs
do not establish that every supported OS has been tested.

## Features

- Intuitive input-folder browser with familiar locations, breadcrumbs, optional subfolders, and multi-camera RAW support through LibRaw (RAF, DNG, CR3, NEF, ARW, RW2, and others).
- Collapsible side panels, progressive RAW detail in Fit view, Retina-aware zoom, and panning that retains loaded detail.
- Film simulations, exposure, DR, highlight and shadow tone, white balance with an R/B grid, color, grain, and effects.
- A recipe for every photograph, plus clear multi-selection in the bottom carousel for linked adjustments.
- JSON recipes, C1–C7 slots, without-film comparison, color-managed JPEG or 8/16-bit TIFF export, and JPEG batch export as ZIP.
- Original files remain untouched and no photographs are sent to a remote service.

## Installation

Python **3.11 or newer** is required for development. The public application download is currently macOS only.

[Download KŌRA 0.2.41 for macOS](https://github.com/avogadro-bit/kora-source/releases/tag/v0.2.41).

The Python module and command are named `kora`. Existing LUT directories and saved
macOS settings are detected automatically. Legacy identifiers are isolated in
`kora/compatibility.py` for backwards compatibility; no user data is deleted.

From the repository directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

On Windows, use `py -3 -m venv .venv`, then `.venv\Scripts\Activate.ps1` in PowerShell.

Install **ExifTool** and make it available on `PATH`: [official website](https://exiftool.org/). On macOS with Homebrew, run `brew install exiftool`. Without ExifTool, metadata and some input profiles are unavailable and rendering can differ.

The desktop app includes **1,569 Lensfun profiles** (database dated 24 September
2026). Source installations need `python -m pip install -e '.[optics]'`.
KŌRA identifies the lens when you open a RAW and offers **Apply available
corrections** in **Lens Corrections** whenever a matching calibration exists.
Distortion and vignetting can also be enabled separately using **Automatic
Profile**. Both remain off until chosen, and existing recipes are respected.
Embedded Leica DNG corrections do not require Lensfun. Unidentified or ambiguous
lenses are left uncorrected. See [current coverage](docs/OPTICS_0.2.35.md) and
[the original validation](docs/OPTICS_AND_NORMALIZATION.md).

### Official LUTs

The `.cube` files are not distributed with this code.

On first launch, the **Setup** dialog provides a direct **Download from Fujifilm** button. After the download, choose the ZIP in the same dialog. The local installer verifies and installs the ten F-Log2 / 65Grid tables. The archive and LUTs are never uploaded to a remote service.

For command-line installation, download **GFX ETERNA 55 v1.10** from the [official Fujifilm LUT page](https://www.fujifilm-x.com/global/support/download/lut/), review its terms, and run:

```sh
python -m kora.lut_install "/path/to/gfx-eterna-55-3d-lut-v110.zip"
```

The installer compares each table against its expected SHA-256. A different or modified archive is rejected. LUTs remain outside the repository in `~/.local/share/kora/luts`. Set `KORA_LUT_DIR` to use another directory. The application links to Fujifilm's server and does not redistribute or substitute missing films.

## Run

```sh
python -m kora gui --port 8766
```

Open the **complete session link shown in the terminal**, then choose **Open Folder**. The server listens only on `127.0.0.1`; keep the terminal open. If the requested port is occupied, the application selects and prints an available port. On macOS, `Launch Kora.command` uses the repository's `.venv` environment.

To add a starting location: `python -m kora gui --root "/path/to/Photos" --port 8766`. Folders are scanned only after explicit selection in the GUI.

## Output dimensions

**Image Size: L**, **Image Aspect: Original**, and **Digital Teleconverter: Off** preserve the dimensions produced by the full-resolution RAW decoder. **JPEG Quality: Fine** changes compression quality only; it does not resize the image. A non-original aspect ratio or digital teleconverter crops the output. Some lens-correction profiles can also alter the usable image boundary. RAW sensor dimensions can include masked margins, so the developed dimensions are not always identical to the nominal sensor dimensions or an in-camera JPEG.

## Tests and sharing

```sh
python -m pip install -e '.[emulation,optics]'
python -m unittest discover -s tests -v
python -m compileall -q kora scripts tests
node --check kora/static/app.js
node --check kora/static/viewer.js
node --test tests/test_connection.cjs tests/test_diagnostics_js.cjs tests/test_film_choices_js.cjs tests/test_viewer.cjs
python scripts/check_release.py
```

Color integration tests are skipped explicitly when the LUTs are not installed. Synthetic tests, HTTP checks, and the installer run without private photos, firmware, or a network connection. The native workbench uses Unicorn and Capstone through the `emulation` extra; they are not needed to run the studio. Node validates JavaScript syntax and runs viewer, connection, diagnostics, and film-choice tests.

The sharing check inspects both tracked and unignored files. It does not replace a manual review of files before publication. See the [sharing audit](docs/SHARING_AUDIT.md), [third-party resources](THIRD_PARTY.md), and [GUI guide](docs/GUI.md).

## Limits

- Extension compatibility depends on the camera model and LibRaw version; not every camera is calibrated.
- The developed preview uses the full-resolution RAW pipeline. Opening a photograph and changing recipes can therefore require substantially more memory and processing time than a reduced preview.
- Adobe RGB export currently requires the macOS system profile; sRGB is portable.
- Undownloaded iCloud files cannot be read. Individual imports are temporary and are removed when the server stops.
- The local service is intended for a personal computer, not public or multi-user hosting. The session link grants access to the local file browser; do not share it.
- Some research scripts reference private reports that are not distributed. They are unnecessary for running or testing the public application.

[Multi-camera normalization](docs/MULTICAMERA_INPUT_V10.md) · [LUT pipeline](docs/OFFICIAL_LUT_STUDIO.md) · [Research history](HISTORY.md)

## License

Original code is released under the [MIT License](LICENSE). This repository grants no license to Fuji files or third-party dependencies. See [THIRD_PARTY.md](THIRD_PARTY.md).
