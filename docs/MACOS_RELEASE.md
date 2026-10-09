# macOS application release

KŌRA can be distributed as a self-contained macOS application.
The application includes Python and the required RAW-processing libraries; users
do not need to install Python or create a virtual environment.

## User installation

1. On an Apple Silicon Mac running macOS 14 or newer, download the ARM64 DMG
   and open it.
2. Drag **KŌRA** into **Applications**.
3. Open the application. It starts a local service bound only to `127.0.0.1`
   and opens its own full-screen macOS window.
4. On first launch, use **Download from Fujifilm**, then **Choose Downloaded ZIP**.
   The application accepts GFX ETERNA 55 v1.10 only, verifies all ten LUT hashes,
   installs them in the user's data directory, and deletes its temporary copy.

The official LUTs are not redistributed in the application. Existing users can
select a previously downloaded LUT ZIP instead of downloading it again. ExifTool
is optional; without it, some camera metadata and input normalization details are
unavailable.

The initial application is ad-hoc signed, but not Apple-notarized. If Gatekeeper
blocks the first launch, Control-click the application, choose **Open**, then
confirm. A Developer ID certificate and Apple notarization should be added before
wide public distribution.

## Maintainer build

Use a clean, portable interpreter so the app does not inherit the build Mac's
minimum OS version. In 0.2.40, Homebrew's Python and several bundled extensions
required macOS 26 even though the app advertised macOS 14. Setting
`MACOSX_DEPLOYMENT_TARGET` or changing the app's plist does not repair prebuilt
libraries. The 0.2.41 build uses python-build-standalone 3.14.8, build 20261003
(the runtime targets macOS 11; KŌRA and its other dependencies require macOS 14).

Install a current [uv](https://docs.astral.sh/uv/) and build in isolation:

```bash
uv python install 3.14.8 --install-dir .venv-runtimes --no-bin
uv venv --python .venv-runtimes/cpython-3.14.8-macos-aarch64-none/bin/python3 .venv-macos-release
uv pip install --python .venv-macos-release/bin/python -c packaging/requirements-macos.txt -e '.[release,optics]' build
.venv-macos-release/bin/python scripts/prepare_release_notices.py
.venv-macos-release/bin/python scripts/build_macos_release.py
```

The script builds and verifies the `.app`, then creates a ZIP, a DMG, dependency
source and notice ZIPs, and `SHA256SUMS.txt` under `dist/release/`. PyInstaller targets the architecture of
the Python interpreter used for the build. Build once on Apple Silicon and once
on Intel to publish both native variants.

For an independent Intel build, use the x86_64 standalone interpreter and set
`KORA_BUILD_VARIANT=x86_64` for **both** the notice and application build commands.
They then use `build/x86_64/`, `dist/macos-x86_64/`, and `dist/release-x86_64/`, so
they cannot remove the arm64 outputs. `KORA_BUILD_VARIANT=arm64` similarly isolates
an ARM build. The variant must match the running interpreter's architecture.
Under Rosetta, run the x86_64 interpreter explicitly; do not merely change a
PyInstaller flag in an arm64 environment. A successful Rosetta run is not a test
on a physical Intel Mac or an older version of macOS.

rawpy 0.27.1 publishes no macOS Intel wheel, for either Python 3.13 or 3.14.
Before installing Kora in the Intel environment, build its missing wheel:

```bash
.venv-intel-release/bin/python -m pip install -r packaging/requirements-intel-build.txt
.venv-intel-release/bin/python scripts/build_rawpy_intel.py
.venv-intel-release/bin/python -m pip install -c packaging/requirements-macos.txt -e '.[release,optics]' build
KORA_BUILD_VARIANT=x86_64 .venv-intel-release/bin/python scripts/prepare_release_notices.py
KORA_BUILD_VARIANT=x86_64 .venv-intel-release/bin/python scripts/build_macos_release.py
```

The Intel helper verifies source checksums, builds LibRaw 0.22.1 with LCMS,
JPEG8-compatible libjpeg-turbo and Jasper under `build/intel-runtime/native`,
repairs library paths into the wheel, and requires the same codec flags as the
arm64 wheel. It never installs these libraries system-wide. It uses the selected
Xcode SDK; use `--sdk /path/to/MacOSX.sdk` if the system command-line tools point
to an SDK newer than the selected compiler can read. This does not change global
Xcode settings. Every new binary targets macOS 14. Libjpeg SIMD is enabled when
NASM is available, otherwise lossy-RAW decoding uses its scalar implementation;
Pillow's JPEG export remains supplied by its own official wheel. The build manifest
records this choice. Do not silently downgrade rawpy to obtain an older wheel.

The manual `macos-release.yml` workflow follows this separation using macOS 14
arm64 and macOS 15 Intel runners. See [portability and validation](PORTABILITY.md)
for target versions and the distinction between an audit and a launch test.

The build checks the interpreter before removing earlier build outputs, then
audits every Mach-O file in the completed bundle. It rejects a minimum OS newer
than `LSMinimumSystemVersion`, missing native architectures, and absolute library
references outside macOS system libraries. The report is saved in
`build/macos-compatibility.json`. This verifies declared binary compatibility;
launch testing on the oldest supported macOS remains necessary.
The model checksum, static assets and lens database in the frozen application are
also checked before packaging. The compatibility report is copied into the release.

## Startup diagnostics

Native startup exceptions now display an alert with the diagnostic file location.
The local service has a 30-second startup deadline instead of leaving the main
thread waiting indefinitely before opening a window. A late service is cancelled.
The diagnostic location is `~/Library/Logs/KŌRA/errors.jsonl`, or the legacy
`~/Library/Logs/Film Recipe Lab/errors.jsonl` if that directory already exists.
Failures before Python itself loads must still be examined in macOS crash reports.
