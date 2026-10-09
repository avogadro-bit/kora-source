"""Build a portable Windows x64 KŌRA distribution on Windows."""
import struct
import sysconfig
from pathlib import Path
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw
from kora import __version__
if __package__:
    from .build_macos_release import digest, reset_directory
else:
    from build_macos_release import digest, reset_directory

ROOT = Path(__file__).resolve().parents[1]


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


def main():
    if not windows_x64_python():
        raise SystemExit('Build this release on Windows x64 using 64-bit Python.')
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
    subprocess.run([sys.executable, str(ROOT / 'scripts/audit_windows_bundle.py'), str(app),
                    '--report', str(release / 'windows-compatibility.json')], cwd=ROOT, check=True)
    shutil.copyfile(ROOT / 'docs' / 'WINDOWS_RELEASE.md', app / 'READ-ME.md')
    archive = Path(shutil.make_archive(str(release / f'Kora-{__version__}-Windows-x64'), 'zip', output, 'Kora'))
    sources = Path(shutil.make_archive(str(release / 'Dependency-Sources-Windows'), 'zip', ROOT / 'build' / 'dependency-sources'))
    notices = Path(shutil.make_archive(str(release / 'Third-Party-Notices-Windows'), 'zip', ROOT / 'build' / 'release-notices'))
    (release / 'SHA256SUMS-Windows.txt').write_text(''.join(f'{digest(p)}  {p.name}\n' for p in (archive, sources, notices)), encoding='utf-8')
    print(f'Windows release: {release}')


if __name__ == '__main__':
    main()
