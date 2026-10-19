# KŌRA for Windows — evaluation build

Windows 10 22H2 / Windows 11 x64 (Intel or AMD), Microsoft Edge WebView2 Evergreen Runtime,
and .NET Framework 4.8 are required. Python is bundled; no Python installation
is needed to run the packaged app. On Windows 11 ARM64, including UTM on
Apple Silicon, this x64 build uses Windows' built-in emulation. It is not a
native ARM64 build; performance there does not represent an Intel/AMD PC.

From 0.2.44, the recommended download is `Kora-<version>-Windows-x64-Setup.exe`.
It installs KŌRA for the current user in `%LOCALAPPDATA%\Programs\Kora`, without
administrator rights, adds a Start menu entry (desktop shortcut optional), checks
for WebView2 and can be removed from Windows Settings › Apps. Installing a newer
version replaces the previous one; LUTs and settings in `%LOCALAPPDATA%\Kora` stay.

The portable ZIP remains available: extract the entire Kora ZIP to a writable
folder, then launch `Kora.exe`. Do not run the executable inside the ZIP or
separate it from `_internal`. The app opens full screen. Use the fullscreen button to return to a window.
Closing the window stops its local service. This build is not code-signed;
Windows may display a publisher warning. Only use downloads you trust.

This evaluation includes rendering, high-resolution previews, zoom,
film choices including experimental Kodachrome 64, and optical corrections. The Windows shell
uses WebView2 with its own settings folder. A stalled local service is
reported after 30 seconds instead of waiting indefinitely. Startup logging
also supports Windows consoles whose encoding cannot display the KŌRA name.

Install the official LUT pack through Setup as on macOS. LUTs and firmware
are not bundled. Images are processed locally and originals are not modified.

- LUTs: `%LOCALAPPDATA%\Kora\luts`
- Error logs: `%LOCALAPPDATA%\Kora\Logs\errors.jsonl`
- Saved UI settings: `%LOCALAPPDATA%\Kora\WebView`

Install WebView2 from https://developer.microsoft.com/microsoft-edge/webview2/.
From 0.2.44, ExifTool 13.59 (64-bit Windows package) is included in `tools\`
beside `Kora.exe`, so camera settings, exposure metadata and lens identification
work on a fresh PC. An `exiftool.exe` on PATH still takes precedence. Adobe RGB export requires a separately installed Adobe RGB (1998)
ICC profile in the Windows system color-profile folder. sRGB needs no extra profile.
Cloud photographs must first be made available offline in File Explorer.

Alternatively, place the optional ExifTool distribution at
`%LOCALAPPDATA%\Kora\tools\exiftool.exe` or `tools\exiftool.exe` beside `Kora.exe`.
Keep its `exiftool_files` directory next to it. These locations need no PATH edit.
Photo paths containing accents and non-Latin characters are passed as UTF-8;
metadata is reused while the source file and selected tool remain unchanged.

RAW decoding uses every CPU core. The rawpy wheel shipped from 0.2.44 is built
by `scripts/build_rawpy_windows.py` with `packaging/libraw-xtrans-deterministic-openmp.patch`.
PyPI's Windows rawpy also used OpenMP, but Fujifilm X-Trans files could then
decode slightly differently from one run to the next (preview, exposure anchor
and pixels at demosaic tile borders). The patched decoder reproduces the
single-threaded LibRaw result exactly, as on macOS.

## Build on Windows

Use 64-bit Python 3.13 in an isolated environment:

```
python -m venv .venv-windows
.venv-windows\Scripts\python scripts/build_rawpy_windows.py
.venv-windows\Scripts\python -m pip install --no-deps build\wheels\rawpy-0.27.1+kora.xtrans1-cp313-cp313-win_amd64.whl
.venv-windows\Scripts\python -m pip install -c packaging/requirements-windows.txt ".[release,optics]"
.venv-windows\Scripts\python scripts/prepare_release_notices.py
.venv-windows\Scripts\python -m scripts.build_windows_release
```

The rawpy build needs Visual Studio 2022 with the C++ x64 tools and Git; it
fetches vcpkg 2026.07.29 like rawpy's own CI. The release build refuses a rawpy
that is not this deterministic OpenMP build. It downloads the ExifTool package
from SourceForge and verifies its SHA-256 (`--exiftool-archive` accepts a local
copy). The installer needs Inno Setup 6 (`ISCC.exe`); `--no-installer` builds
only the ZIP. `scripts/smoke_windows_installer.py` installs the setup silently
in a Unicode folder, starts the installed app and uninstalls it.

The Windows workflow builds on a real Windows runner, runs tests and a packaged
server and native WebView2 smoke tests, and uploads artifacts for review. The
packaged executable also develops a checksum-verified public Canon CR2 sample,
renders PROVIA, Classic Negative, Pro Neg. Hi and Kodachrome previews, serves a source-detail tile,
and exports a full-resolution JPEG with an ICC profile. The sample is downloaded
from rawpy's test data (rawsamples.ch, CC BY-NC-SA 4.0), used temporarily and never
included in the application or release artifacts. The official LUT pack is also
downloaded from Fujifilm, verified and installed only in the temporary test
directory. It is never added to the package. The workflow does not publish a release
automatically. A real-user visual check and RAW/export test remain necessary
before declaring the Windows build production-ready.

The smoke test runs a relocated copy of the entire app in a path with spaces and
non-ASCII characters, from an unrelated working directory. A build audit also
rejects missing resources or native extensions with the wrong architecture before
creating the ZIP. WebView2's managed DLLs are checked separately from its native
loader. The report is `windows-compatibility.json` beside the archive.

If that test computer cannot validate Fujifilm's TLS certificate, use an official
ZIP downloaded separately: `python scripts/smoke_windows_release.py --lut-archive
path/to/fuji.zip`. The normal ten LUT checksum checks still apply; TLS verification
is never disabled. The smoke terminates only its own process tree and reports a
temporary-file cleanup problem without hiding the original failure.

The fixed Windows Server 2022 CI runner exercises Windows code and packaging; it
does not establish Windows 10 or Windows 11 client compatibility. See
[portability and validation](PORTABILITY.md) for remaining OS/hardware tests.
