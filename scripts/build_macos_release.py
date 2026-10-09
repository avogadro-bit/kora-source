"""Build the self-contained macOS application, ZIP, DMG, and checksums."""
import hashlib
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys

from kora import __version__
if __package__:
    from .release_paths import release_paths
else:
    from release_paths import release_paths


ROOT = Path(__file__).resolve().parents[1]
VERSION = __version__


def run(*command):
    print("+", " ".join(map(str, command)), flush=True)
    subprocess.run([str(part) for part in command], cwd=ROOT, check=True)


def reset_directory(path):
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def main():
    if sys.platform != "darwin":
        raise SystemExit("The macOS release must be built on macOS.")
    architecture = platform.machine().lower()
    if architecture not in {"arm64", "x86_64"}:
        raise SystemExit(f"Unsupported macOS architecture: {architecture}")

    # A deployment-target environment variable cannot make an existing runtime
    # compatible with older systems. Reject it before removing previous builds.
    variant = os.environ.get('KORA_BUILD_VARIANT', '')
    if variant and variant != architecture:
        raise SystemExit('KORA_BUILD_VARIANT must match the Python interpreter architecture.')
    if __package__:
        from .audit_macos_bundle import inspect_binary
    else:
        from audit_macos_bundle import inspect_binary
    from PyInstaller.depend.bindepend import get_python_library_path
    runtime = get_python_library_path()
    if runtime is None:
        raise SystemExit('Could not locate the Python runtime library.')
    runtime_check = inspect_binary(runtime, '14.0', architecture)
    # The unfrozen runtime still has absolute install names. PyInstaller relocates
    # them; the complete bundle is checked again below.
    if any('requires macOS' in issue or 'missing ' in issue for issue in runtime_check['problems']):
        raise SystemExit(f"Incompatible Python runtime: {runtime_check['problems']}")

    build, app_dist, release = release_paths(ROOT)
    work = build / 'pyinstaller'
    staging = build / 'dmg-root'
    for path in (work, app_dist, release, staging):
        reset_directory(path)

    run("swift", ROOT / "scripts" / "build_app_icon.swift", ROOT, build / 'AppIcon.iconset')
    run("iconutil", "-c", "icns", build / "AppIcon.iconset", "-o", build / "AppIcon.icns")
    run(
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--workpath",
        work,
        "--distpath",
        app_dist,
        ROOT / "packaging" / "KoraMacOS.spec",
    )

    app = app_dist / "KŌRA.app"
    if not app.is_dir():
        raise SystemExit(f"Application bundle was not produced: {app}")
    run(sys.executable, ROOT / 'scripts' / 'audit_macos_bundle.py', app,
        '--architecture', architecture, '--report', build / 'macos-compatibility.json')
    run(sys.executable, ROOT / 'scripts' / 'audit_package_assets.py', app / 'Contents' / 'Resources')
    # Ad-hoc signing catches altered nested binaries and avoids an entirely
    # unsigned bundle. Public notarization still requires an Apple Developer ID.
    run("codesign", "--force", "--deep", "--sign", "-", app)
    run("codesign", "--verify", "--deep", "--strict", app)

    base = f"Kora-{VERSION}-macOS-{architecture}"
    archive = release / f"{base}.zip"
    image = release / f"{base}.dmg"
    run("ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", app, archive)

    run("ditto", app, staging / app.name)
    (staging / "Applications").symlink_to("/Applications")
    shutil.copyfile(build / "AppIcon.icns", staging / ".VolumeIcon.icns")
    run("SetFile", "-a", "C", staging)
    run(
        "hdiutil",
        "create",
        "-volname",
        "KŌRA",
        "-srcfolder",
        staging,
        "-ov",
        "-format",
        "UDZO",
        image,
    )

    checksums = release / "SHA256SUMS.txt"
    sources = Path(shutil.make_archive(str(release / "Dependency-Sources"), "zip", build / "dependency-sources"))
    notices = Path(shutil.make_archive(str(release / "Third-Party-Notices"), "zip", build / "release-notices"))
    shutil.copyfile(build / 'macos-compatibility.json', release / 'macos-compatibility.json')
    checksums.write_text(
        "".join(f"{digest(path)}  {path.name}\n" for path in (archive, image, sources, notices)),
        encoding="utf-8",
    )
    print(f"Release artifacts: {release}")


if __name__ == "__main__":
    main()
