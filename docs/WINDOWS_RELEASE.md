# KŌRA for Windows — evaluation build

Windows 10/11 x64 (Intel or AMD), Microsoft Edge WebView2 Evergreen Runtime,
and .NET Framework 4.8 are required. Python is bundled; no Python installation
is needed to run the packaged app. On Windows 11 ARM64, including UTM on
Apple Silicon, this x64 build uses Windows' built-in emulation. It is not a
native ARM64 build; performance there does not represent an Intel/AMD PC.

Extract the entire Kora ZIP to a writable folder, then launch `Kora.exe`.
Do not run the executable inside the ZIP or separate it from `_internal`.
The app opens full screen. Use the fullscreen button to return to a window.
Closing the window stops its local service. This build is not code-signed;
Windows may display a publisher warning. Only use downloads you trust.

This evaluation includes the rendering, high-resolution previews, zoom,
film choices and optical corrections from KŌRA 0.2.41. The Windows shell
uses WebView2 with its own settings folder. A stalled local service is
reported after 30 seconds instead of waiting indefinitely. Startup logging
also supports Windows consoles whose encoding cannot display the KŌRA name.

Install the official LUT pack through Setup as on macOS. LUTs and firmware
are not bundled. Images are processed locally and originals are not modified.

- LUTs: `%LOCALAPPDATA%\Kora\luts`
- Error logs: `%LOCALAPPDATA%\Kora\Logs\errors.jsonl`
- Saved UI settings: `%LOCALAPPDATA%\Kora\WebView`

Install WebView2 from https://developer.microsoft.com/microsoft-edge/webview2/.
ExifTool is optional; if used, install `exiftool.exe` and its supporting files
on PATH. Adobe RGB export requires a separately installed Adobe RGB (1998)
ICC profile in the Windows system color-profile folder. sRGB needs no extra profile.
Cloud photographs must first be made available offline in File Explorer.

## Build on Windows

Use 64-bit Python 3.13 in an isolated environment:

```
python -m venv .venv-windows
.venv-windows\Scripts\python -m pip install ".[release,optics]" rawpy==0.27.1 lensfunpy==1.18.0
.venv-windows\Scripts\python scripts/prepare_release_notices.py
.venv-windows\Scripts\python -m scripts.build_windows_release
```

The Windows workflow builds on a real Windows runner, runs tests and a packaged
server and native WebView2 smoke tests, and uploads artifacts for review. The
packaged executable also develops a checksum-verified public Canon CR2 sample,
renders PROVIA, Classic Negative and Pro Neg. Hi previews, serves a source-detail tile,
and exports a full-resolution JPEG with an ICC profile. The sample is downloaded
from rawpy's test data (rawsamples.ch, CC BY-NC-SA 4.0), used temporarily and never
included in the application or release artifacts. The official LUT pack is also
downloaded from Fujifilm, verified and installed only in the temporary test
directory. It is never added to the package. The workflow does not publish a release
automatically. A real-user visual check and RAW/export test remain necessary
before declaring the Windows build production-ready.
