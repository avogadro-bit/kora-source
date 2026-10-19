# KŌRA 0.2.44 — Faster RAW loading and a Windows installer

RAW files open faster on Apple Silicon Macs. The app now ships rawpy 0.27.1 /
LibRaw 0.22.1 built with OpenMP (`0.27.1+kora.xtrans1`), so demosaicing uses
every core. Fujifilm X-Trans files benefit most: on an M4 Max, an X-T5 RAF reaches
its first full-resolution view in 3.9 s instead of 13.0 s, an X-M5 RAF in 3.2 s
instead of 8.4 s. Other cameras gain 1.0–1.9× in decoding.

LibRaw's OpenMP code made X-Trans output vary between runs (racing demosaic
tiles and half-size copies). `packaging/libraw-xtrans-deterministic-openmp.patch`
orders that work, and the decoded pixels are bit-identical to single-threaded
LibRaw on all 21 readable test RAWs from 11 cameras, run after run. The official
Windows rawpy wheel already used OpenMP without this fix; the Windows build now
compiles the patched decoder too.

Screen previews abandoned by a newer slider value stop between rendering stages
instead of finishing in the background. During a simulated slider drag on a 60 MP
DNG, the last value appears after 1.75 s instead of 3.0 s.

Windows: a per-user installer (`Kora-0.2.44-Windows-x64-Setup.exe`, Inno Setup)
joins the portable ZIP, and ExifTool 13.59 is bundled in `tools\` so camera
metadata works on a fresh PC.

## Validation

- macOS arm64 decoding: bit-identical full-resolution and preview buffers on 21
  RAWs, deterministic across two runs. See `docs/LOADING_0.2.44.md`.
- 327 Python tests and 5 JavaScript suites passed on macOS.
- Packaged arm64 app: 140 Mach-O binaries audited for macOS 14, ad-hoc signature
  verified, `scripts/smoke_macos_release.py` passed with an X-T5 RAF (Kodachrome
  preview, tile, 7752 × 5178 JPEG export with ICC profile, original unchanged).
  The native window was not exercised by script.
- Not yet run: the Windows build (patched rawpy, ExifTool, installer and their
  smoke tests) needs the GitHub Windows workflow; the macOS Intel build keeps
  the 0.2.43 single-threaded decoder.
