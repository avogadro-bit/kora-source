# Portability and what the checks establish

Kora packages Python, the RAW decoder, numeric libraries, color profiles for sRGB,
the lens database and the Kodachrome model. The app does not depend on an existing
Python/Conda installation. Fuji LUTs are installed separately through Setup.

## Targets

| Target | Current release policy | Remaining validation |
| --- | --- | --- |
| macOS, Apple Silicon | Native arm64, macOS 14+ | Launch/render/export on the oldest supported OS and each new major OS |
| macOS, Intel | Separate native x86_64 package, macOS 14+ | A Rosetta test is useful but does not replace a physical Intel Mac test |
| Windows 10 22H2 / Windows 11, Intel/AMD | x64 package; WebView2 Evergreen and .NET Framework 4.8 | Client-OS tests; a Windows Server CI runner is not a Windows 10 test |
| Windows 11, ARM | x64 package through Windows emulation | Native ARM64 is not shipped; performance differs from an x64 PC |

These are target policies, not a claim that every combination has been run.
The Mac binary audit establishes the declared deployment target of every bundled
Mach-O. A report saying `compatible: true` is not a successful GUI launch on all
versions of macOS. The Windows audit establishes native architecture and essential
files; it does not infer a minimum OS from the PE header.

The 0.2.43 arm64 bundle audit found 139 Mach-O components. Of these, 100 declare
macOS 14.0, including NumPy 2.5.3, SciPy 1.18.1 and lensfunpy 1.18.0; the other 39
declare 11.0. Lowering `LSMinimumSystemVersion` alone would therefore break older
Macs. Supporting macOS 12/13 requires a separate compatible dependency build and
real OS tests, not an installer-label change. The separate 0.2.43 Intel bundle
contains 156 audited x86_64 components; its maximum declared requirement is also
macOS 14.0. Both audits passed with no external absolute library paths.

Local validation on 2026-10-08 used an Apple Silicon M4 Max running macOS 27.0.
Both packaged applications passed the same test, with the Intel app running
under Rosetta: develop a 60.5 MP DNG from a relocated Unicode path, render a
1400 × 931 Kodachrome preview and a 512 × 512 detail tile, and export a
9536 × 6344 JPEG with an ICC profile, without installed Fuji LUTs. The original
RAW checksum remained unchanged. The Intel environment also passed seven
Kodachrome tests and nine portability tests. These checks validate the packaged
local service; they do not establish operation on a physical Intel Mac, on macOS
14, or in the native window on every OS version.

The Windows 0.2.43 x64 package was built and run in Windows 11 ARM64
(build 26300), using x64 emulation. Its audit passed on 126 native components.
The relocated application passed the actual WebView2 window check, with Unicode
application/photo paths: Provia, Classic Negative, Pro Neg Hi and Kodachrome 64
previews at 1024 × 683, a 256 × 256 detail tile, and a 1944 × 1296 JPEG export
with an ICC profile. The source suite ran 311 tests: 285 passed, 26 skipped
because Fuji assets were absent during unit tests; the later packaged smoke
installed verified Fuji LUTs temporarily and exercised those four films.
This establishes neither Windows 10 nor native Intel/AMD hardware compatibility.
The VM's certificate store rejected the Fuji download; the successful test used
the local official archive with all ten LUT checksums verified, without disabling
TLS verification. The LUTs are not included in any application archive.

There is currently no native Windows ARM64 release with the full optical pipeline:
rawpy publishes ARM64 wheels, but lensfunpy 1.18.0 publishes Windows x64 wheels only.
Windows 11 x64 emulation is the current route. Windows 10 on ARM is not a target.

rawpy 0.27.1 also has no macOS Intel wheel. The Intel build therefore uses
`scripts/build_rawpy_intel.py` to build the same RAW version and codecs from
checksum-verified sources in an isolated directory, then repairs its library
paths into a standalone wheel. Changing from Python 3.14 to 3.13 does not avoid
this missing upstream wheel. See the [Intel build instructions](MACOS_RELEASE.md).

## Repeatable build checks

- `scripts/audit_macos_bundle.py`: architecture, deployment targets and external
  absolute library paths; includes the maximum required version in its JSON report.
- `scripts/audit_windows_bundle.py`: x64 executable, Python runtime, native numeric,
  RAW and lens extensions, the correct native WebView2 loader, managed WebView2 and
  Python.NET assemblies. Managed AnyCPU DLLs are not mistaken for x86 native code.
- `scripts/audit_package_assets.py`: assets, lens database and integrity of the
  packaged Kodachrome tables. It examines the frozen application, not the checkout.
- `scripts/smoke_windows_release.py`: moves the app to a folder containing spaces
  and non-ASCII characters, uses a separate working directory and Unicode photo
  paths, then exercises its packaged GUI/RAW preview/tile/export. Fuji files and
  the public RAW regression sample stay temporary. Kodachrome is included.
  `--lut-archive` accepts an already downloaded official ZIP, retaining all hash
  checks, when the test computer cannot reach Fujifilm with its TLS trust store.
  The smoke stops only its own process tree and preserves an original test error
  if Windows delays removal of a temporary file.
- `scripts/smoke_macos_release.py`: runs a relocated Mac app and a copied RAW in
  Unicode paths, with no Fuji LUTs, and checks Kodachrome preview, detail tile and
  full-resolution JPEG export with its ICC profile. It tests the packaged local
  service, not the native window, and preserves the original RAW checksum.

Run the platform build script; both audits are mandatory before creating the ZIP
or DMG. Do not reuse release-notices from a different interpreter or architecture.
Preserve the compatibility JSON, dependency inventory and checksums with artifacts.

The source CI matrix explicitly names macOS 14/26 arm64, macOS 15 Intel,
Windows Server 2022/2025 x64 and Linux, and exercises supported Python versions.
The manual Mac release workflow builds separate arm64 and x86_64 packages.
Configuring those workflows does not mean they have run or passed; check the actual
job and artifact report before publishing.

## External components

On Mac, the window uses the WebKit version supplied by macOS. On Windows, the
WebView2 loader/managed bridge are bundled but the browser runtime is installed by
Microsoft. The app deliberately never falls back to Internet Explorer. Windows
startup errors name WebView2/.NET and give the diagnostic file location.

ExifTool is optional and is not bundled. Without it, extended metadata and some
metadata-dependent normalization/optics are unavailable; rendering a RAW can still
work. This can explain differences between a developer's machine and a fresh PC.
On Windows it can also be installed as `%LOCALAPPDATA%/Kora/tools/exiftool.exe`
or beside the portable app at `tools/exiftool.exe`; keep the official distribution's
companion `exiftool_files` folder alongside the executable. No PATH edit is needed
for these locations. Kora 0.2.43 sends Windows photo paths to ExifTool as UTF-8
arguments and avoids opening a console window for each read. Metadata is cached
by the file's identity/size/timestamps and selected tool; repeated UI requests can
reuse it, while file changes invalidate the cache.
Adobe RGB output also requires that ICC profile on the computer; sRGB is bundled.
Cloud photos must be downloaded locally before they can be read.

Unsigned/ad-hoc-signed binaries can be blocked by Gatekeeper or Windows publisher
checks. An OS compatibility audit does not establish notarization or publisher
trust. Developer signing/notarization is a separate release step.

## Upstream references, checked 2026-10-08

- [PyInstaller architecture and bundling rules](https://pyinstaller.org/en/stable/feature-notes.html#macos-multi-arch-support): native packages must contain the matching architecture; merging frozen executables with `lipo` is not a universal-app build.
- [lensfunpy 1.18.0 release files](https://pypi.org/project/lensfunpy/1.18.0/#files) and [rawpy release files](https://pypi.org/project/rawpy/#files): current binary distributions.
- [Microsoft x64 emulation on Arm](https://learn.microsoft.com/en-us/windows/arm/apps-on-arm-x86-emulation): Windows 11 x64 emulation.
- [Microsoft Edge/WebView2 operating systems](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-supported-operating-systems): Windows 10 22H2 runtime updates continue until at least October 2028. That does not by itself test Kora on Windows 10.
- [pywebview dependencies](https://pywebview.flowrl.com/guide/installation.html): OS-specific desktop bridge dependencies.
- [GitHub runner table](https://docs.github.com/en/actions/reference/runners/github-hosted-runners): the architecture behind each CI label.
