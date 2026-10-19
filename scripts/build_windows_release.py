"""Build a portable Windows x64 KŌRA distribution on Windows."""
import argparse
import hashlib
import os
import struct
import sysconfig
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
from urllib.request import urlopen
import zipfile

from PIL import Image, ImageDraw
from kora import __version__
if __package__:
    from .audit_windows_bundle import VC_RUNTIME, pe_machine
    from .build_macos_release import digest, reset_directory
    from .build_rawpy_openmp import require_release_rawpy
else:
    from audit_windows_bundle import VC_RUNTIME, pe_machine
    from build_macos_release import digest, reset_directory
    from build_rawpy_openmp import require_release_rawpy

ROOT = Path(__file__).resolve().parents[1]
# Official 64-bit Windows ExifTool package (bundles its own Strawberry Perl).
# exiftool.org keeps only the newest version; SourceForge keeps every release.
EXIFTOOL_VERSION = '13.59'
EXIFTOOL_URL = f'https://sourceforge.net/projects/exiftool/files/exiftool-{EXIFTOOL_VERSION}_64.zip/download'
EXIFTOOL_SHA256 = '44b512b25af500724ba579d0a53c8fc5851628b692dd5e5d94ae4a15c2cba9ec'


def windows_x64_python():
    # Windows on Arm can report platform.machine() == 'ARM64' even when the
    # process is an emulated x64 Python. Build for the interpreter, not the host.
    return (sys.platform == 'win32' and sysconfig.get_platform() == 'win-amd64'
            and struct.calcsize('P') == 8)


def build_icon():
    # Code-native counterpart of packaging/AppIcon.svg, rendered at 4x.
    image = Image.new('RGBA', (1024, 1024))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((48, 48, 976, 976), radius=204, fill='#111412', outline='#293029', width=3)
    draw.line((360, 348, 360, 694), fill='#c9ccc3', width=18)
    draw.line((654, 348, 397, 521, 661, 694), fill='#c9ccc3', width=18)
    draw.line((353, 264, 660, 264), fill='#9aa993', width=12)
    image.save(ROOT / 'build' / 'Kora.ico', sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])


def exiftool_archive(path=None):
    """Return the checksum-verified ExifTool ZIP, downloading it only if needed."""
    archive = Path(path) if path else ROOT / 'build' / 'exiftool' / f'exiftool-{EXIFTOOL_VERSION}_64.zip'
    if not archive.is_file():
        if path:
            raise SystemExit(f'ExifTool archive not found: {archive}')
        archive.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(EXIFTOOL_URL, timeout=120) as response:
            archive.write_bytes(response.read())
    with archive.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual != EXIFTOOL_SHA256:
        raise SystemExit(f'ExifTool {EXIFTOOL_VERSION} archive checksum mismatch: {actual}')
    return archive


def bundle_exiftool(app, archive):
    """Install ExifTool as tools/exiftool.exe, where Kora looks beside Kora.exe."""
    tools = app / 'tools'
    shutil.rmtree(tools, ignore_errors=True)
    prefix = PurePosixPath(f'exiftool-{EXIFTOOL_VERSION}_64')
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            name = PurePosixPath(member.filename)
            if member.is_dir() or name.parts[:1] != prefix.parts:
                continue
            relative = PurePosixPath(*name.parts[1:])
            if not relative.parts or '..' in relative.parts or relative.is_absolute():
                raise SystemExit(f'Unexpected ExifTool archive entry: {member.filename}')
            if relative == PurePosixPath('exiftool(-k).exe'):
                # The (-k) name pauses for a key press; Kora runs it headless.
                relative = PurePosixPath('exiftool.exe')
            elif relative.parts[0] != 'exiftool_files' and relative.name != 'README.txt':
                continue
            target = tools.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open(member) as stream, target.open('wb') as output:
                shutil.copyfileobj(stream, output)
    if not (tools / 'exiftool.exe').is_file() or not (tools / 'exiftool_files' / 'LICENSE').is_file():
        raise SystemExit('The ExifTool archive does not contain the expected Windows package.')
    return tools


def vc_redist_x64():
    """Newest x64 Visual C++ runtime folder of an installed Visual Studio, if any."""
    vswhere = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'),
                   'Microsoft Visual Studio', 'Installer', 'vswhere.exe')
    if not vswhere.is_file():
        return None
    # -products * also lists Build Tools, which carry the same redistributable.
    result = subprocess.run([str(vswhere), '-all', '-products', '*', '-property', 'installationPath', '-utf8'],
                            capture_output=True, encoding='utf-8', check=False)
    folders = []
    for install in filter(None, map(str.strip, result.stdout.splitlines())):
        for crt in Path(install, 'VC', 'Redist', 'MSVC').glob('*/x64/Microsoft.VC*.CRT'):
            version = crt.parent.parent.name.split('.')
            if all(part.isdigit() for part in version) and (crt / 'msvcp140.dll').is_file():
                folders.append((tuple(map(int, version)), crt))
    return max(folders, key=lambda folder: folder[0])[1] if folders else None


def is_x64(path):
    try:
        return pe_machine(path) == 'x64'
    except (OSError, ValueError):
        return False


def bundle_vc_runtime(app):
    """Add the x64 Visual C++ runtime that PyInstaller could not take from System32.

    On Windows on Arm, System32 holds ARM64X builds that PyInstaller refuses for
    an x64 bundle, so rawpy and lensfunpy would ship without MSVCP140.dll.
    """
    resources = app / '_internal'
    present = {path.name.lower(): path for path in resources.iterdir()}
    missing = [name for name in VC_RUNTIME if not is_x64(present.get(name.lower(), resources / name))]
    if not missing:
        return []
    redist = vc_redist_x64()
    if redist is None:
        raise SystemExit(f'No x64 {", ".join(missing)} for the bundle, and no Visual Studio x64 redistributable '
                         r'(VC\Redist\MSVC\*\x64\Microsoft.VC143.CRT) was found; install the C++ x64 build tools.')
    for name in missing:
        source = redist / name.lower()
        if not is_x64(source):
            raise SystemExit(f'{source} is not an x64 Visual C++ runtime DLL')
        shutil.copyfile(source, present.get(name.lower(), resources / name))
        print(f'Bundled {name} from {redist}', flush=True)
    return missing


def find_inno_setup():
    candidates = [shutil.which('iscc')]
    # Without administrator rights, Inno Setup installs in %LOCALAPPDATA%\Programs.
    for variable, folder in (('ProgramFiles(x86)', ''), ('ProgramFiles', ''), ('LOCALAPPDATA', 'Programs')):
        if os.environ.get(variable):
            candidates.append(str(Path(os.environ[variable]) / folder / 'Inno Setup 6' / 'ISCC.exe'))
    return next((c for c in candidates if c and Path(c).is_file()), None)


def build_installer(release):
    """Per-user Inno Setup installer for the same files as the portable ZIP."""
    compiler = find_inno_setup()
    if compiler is None:
        raise SystemExit('Inno Setup 6 (ISCC.exe) is required for the installer; use --no-installer to skip it.')
    subprocess.run([compiler, f'/DAppVersion={__version__}', f'/DSourceDir={ROOT / "dist" / "windows" / "Kora"}',
                    f'/DOutputDir={release}', f'/DIconFile={ROOT / "build" / "Kora.ico"}',
                    str(ROOT / 'packaging' / 'KoraWindows.iss')], cwd=ROOT, check=True)
    installer = release / f'Kora-{__version__}-Windows-x64-Setup.exe'
    if not installer.is_file():
        raise RuntimeError('The Windows installer was not produced')
    return installer


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exiftool-archive', type=Path,
                        help=f'Local exiftool-{EXIFTOOL_VERSION}_64.zip; its checksum is still verified')
    parser.add_argument('--no-installer', action='store_true', help='Build only the portable ZIP')
    args = parser.parse_args(argv)
    if not windows_x64_python():
        raise SystemExit('Build this release on Windows x64 using 64-bit Python.')
    # PyPI's Windows rawpy uses OpenMP without the X-Trans ordering patch.
    print('rawpy:', require_release_rawpy(require_patched=True), flush=True)
    work, output, release = (ROOT / 'build' / 'windows-pyinstaller', ROOT / 'dist' / 'windows', ROOT / 'dist' / 'windows-release')
    for path in (work, output, release):
        reset_directory(path)
    build_icon()
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                    '--workpath', str(work), '--distpath', str(output),
                    str(ROOT / 'packaging' / 'KoraWindows.spec')], cwd=ROOT, check=True)
    app = output / 'Kora'
    if not (app / 'Kora.exe').is_file():
        raise RuntimeError('Kora.exe was not produced')
    bundle_vc_runtime(app)
    bundle_exiftool(app, exiftool_archive(args.exiftool_archive))
    subprocess.run([sys.executable, str(ROOT / 'scripts/audit_windows_bundle.py'), str(app),
                    '--report', str(release / 'windows-compatibility.json')], cwd=ROOT, check=True)
    shutil.copyfile(ROOT / 'docs' / 'WINDOWS_RELEASE.md', app / 'READ-ME.md')
    archive = Path(shutil.make_archive(str(release / f'Kora-{__version__}-Windows-x64'), 'zip', output, 'Kora'))
    sources = Path(shutil.make_archive(str(release / 'Dependency-Sources-Windows'), 'zip', ROOT / 'build' / 'dependency-sources'))
    notices = Path(shutil.make_archive(str(release / 'Third-Party-Notices-Windows'), 'zip', ROOT / 'build' / 'release-notices'))
    artifacts = [archive, sources, notices]
    if not args.no_installer:
        artifacts.insert(1, build_installer(release))
    (release / 'SHA256SUMS-Windows.txt').write_text(''.join(f'{digest(p)}  {p.name}\n' for p in artifacts), encoding='utf-8')
    print(f'Windows release: {release}')


if __name__ == '__main__':
    main()
