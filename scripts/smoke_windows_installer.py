"""Install the Windows setup silently, start the installed app, then uninstall it.

Runs on Windows after scripts/build_windows_release.py. The installation goes
to a temporary folder whose name contains spaces and non-ASCII characters; the
test verifies the bundled ExifTool, the local service, that uninstalling is
refused while the app runs, and that a later uninstall removes every file.
"""
from pathlib import Path
import json
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from smoke_windows_release import managed_app, smoke_workspace  # noqa: E402


def silent(executable, *arguments, check=True):
    return subprocess.run([str(executable), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', *arguments],
                          check=check, timeout=600)


def uninstall(target):
    silent(target/'unins000.exe')
    for _ in range(20):  # The uninstaller finishes removing files after it returns.
        if not target.exists():
            return
        time.sleep(.5)
    left = [str(path.relative_to(target)) for path in target.rglob('*') if path.is_file()]
    raise RuntimeError(f'The uninstaller left {len(left)} files behind, such as {left[:5]}')


def main():
    if sys.platform != 'win32':
        raise SystemExit('The installer test runs on Windows.')
    setups = sorted((ROOT/'dist'/'windows-release').glob('Kora-*-Windows-x64-Setup.exe'))
    if len(setups) != 1:
        raise SystemExit(f'Expected one installer, found {[p.name for p in setups]}')
    with smoke_workspace() as temporary:
        target = Path(temporary)/'Programmes été'/'KŌRA'
        try:
            silent(setups[0], '/CURRENTUSER', f'/DIR={target}')
            for required in ('Kora.exe', 'tools/exiftool.exe', 'tools/exiftool_files/LICENSE', 'unins000.exe'):
                if not (target/required).is_file():
                    raise SystemExit(f'The installer did not install {required}')
            version = subprocess.run([str(target/'tools'/'exiftool.exe'), '-ver'], check=True,
                                     capture_output=True, text=True, timeout=60).stdout.strip()
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            with managed_app(target/'Kora.exe', '--no-browser', '--port', port, cwd=temporary) as process:
                for _ in range(60):
                    if process.poll() is not None:
                        raise RuntimeError(f'Installed app exited: {process.returncode}')
                    try:
                        with urlopen(f'http://127.0.0.1:{port}', timeout=1) as response:
                            page = response.read().decode('utf-8')
                        break
                    except OSError:
                        time.sleep(.5)
                else:
                    raise RuntimeError('Installed app did not start within 30 seconds')
                # AppMutex: a silent uninstall must refuse to run while KŌRA is open.
                if not silent(target/'unins000.exe', check=False).returncode or not (target/'Kora.exe').is_file():
                    raise RuntimeError('The uninstaller ran while the installed app was open')
            if '<title>KŌRA</title>' not in page:
                raise RuntimeError('Installed app served an unexpected page')
        finally:
            # Also after a failed check: otherwise the user keeps an orphan
            # uninstall entry and Start menu shortcut for a deleted folder.
            if (target/'unins000.exe').is_file():
                uninstall(target)
        print(json.dumps({'installer': setups[0].name, 'exiftool': version, 'installed_server': 'ok',
                          'uninstall': 'ok'}))


if __name__ == '__main__':
    main()
