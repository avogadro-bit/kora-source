# KŌRA 0.2.41 — macOS compatibility correction

The 0.2.40 macOS package advertised macOS 14 but contained a Python runtime and
58 other native components that required macOS 15 or 26. This could prevent
startup on an otherwise supported Apple Silicon Mac. The runtime is now a
portable Python 3.14.8 build; photo-processing dependencies retain their 0.2.40
versions.

The release builder rejects incompatible runtimes before removing old artifacts,
then checks every bundled native binary against the declared macOS minimum and
architecture. It also rejects dependencies on non-system absolute library paths.
Runtime licenses now come from the matching portable Python distribution.

Startup exceptions display a native error dialog with the diagnostic file
location. The local service has a 30-second startup deadline; a stalled service
no longer leaves the main thread waiting indefinitely before window creation.
This cannot catch failures occurring before the Python runtime loads.

## Validation

- All 139 bundled Mach-O binaries declare macOS 11 or 14 compatibility, include
  arm64, and have no non-system absolute library references. The same audit
  rejects 59 binaries in the original 0.2.40 bundle.
- 282 Python tests and 16 JavaScript checks passed.
- Native 0.2.41 window opened and displayed a Leica DNG with PROVIA at high quality.
- With an empty home directory and a system-only PATH, the packaged local service
  became ready in 0.53 seconds on the development Mac. Initial LUT setup, neutral
  and PROVIA previews (1800 × 1197), and a full-resolution tile (512 × 512) passed.
- Ad-hoc signature and DMG checksum verification passed.

These checks ran on the development Mac. Startup on the reported MacBook Air M4
and on macOS 14 has not yet been verified. The user reports Tahoe 26.6.2 on the Air,
which is newer than the original runtime's minimum. The deployment-target defect
therefore does not explain that specific failure by itself. An actual 0.2.41
retest and, if it still fails, diagnostics from the Air are needed to identify
the cause. The application remains ad-hoc signed, without Apple notarization.
