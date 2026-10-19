"""Install the Windows setup silently, start the installed app, then uninstall it.

Runs on Windows after scripts/build_windows_release.py. The installation goes
to a temporary folder whose name contains spaces and non-ASCII characters; the
test verifies the bundled ExifTool, the local service and a clean uninstall.
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


def silent(executable, *arguments):
    subprocess.run([str(executable), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', *arguments],
                   check=True, timeout=600)


def main():
    if sys.platform != 'win32':
        raise SystemExit('The installer test runs on Windows.')
    setups = sorted((ROOT/'dist'/'windows-release').glob('Kora-*-Windows-x64-Setup.exe'))
    if len(setups) != 1:
        raise SystemExit(f'Expected one installer, found {[p.name for p in setups]}')
    with smoke_workspace() as temporary:
        target = Path(temporary)/'Programmes été'/'KŌRA'
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
        if '<title>KŌRA</title>' not in page:
            raise RuntimeError('Installed app served an unexpected page')
        silent(target/'unins000.exe')
        for _ in range(20):  # The uninstaller finishes removing files after it returns.
            if not (target/'Kora.exe').exists():
                break
            time.sleep(.5)
        else:
            raise RuntimeError('The uninstaller left Kora.exe behind')
        print(json.dumps({'installer': setups[0].name, 'exiftool': version, 'installed_server': 'ok',
                          'uninstall': 'ok'}))


if __name__ == '__main__':
    main()
