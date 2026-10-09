"""Start the packaged server, verify its assets/API, then stop our own process."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import socket
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

from kora import diagnostics
from kora.studio import studio_status
from kora.lut_install import install_archive
from kora.official_luts import MANIFEST
from kora.windows_app import expected_films

ROOT = Path(__file__).resolve().parents[1]

# Public regression sample from rawpy / rawsamples.ch, CC BY-NC-SA 4.0.
# Downloaded into the temporary test directory; never bundled with Kora.
RAW_URL = ('https://raw.githubusercontent.com/letmaik/rawpy/'
           'a39c2e7a44911889c3360891012f862f904ba551/test/RAW_CANON_40D_SRAW_V103.CR2')
RAW_SHA256 = '152382ce4dbf644899d12b41b4c577f07638aa3ec5745ac344c36bad93826125'


def stop_process(process):
    if process.poll() is not None:
        return
    if sys.platform == 'win32':
        # Kill only this smoke's PID and descendants, before its launcher exits
        # and Windows can no longer identify the process tree.
        result = subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                capture_output=True, timeout=15,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode and process.poll() is None:
            raise RuntimeError(f'Could not stop smoke process tree {process.pid}: '
                               + result.stderr.decode(errors='replace'))
    else:
        process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


@contextmanager
def managed_app(*command, **options):
    process = subprocess.Popen(list(map(str, command)), **options)
    try:
        yield process
    except BaseException as original:
        try:
            stop_process(process)
        except Exception as cleanup:
            original.add_note(f'Also failed to stop the smoke process: {cleanup}')
        raise
    else:
        stop_process(process)


@contextmanager
def smoke_workspace():
    directory = tempfile.mkdtemp(prefix='kora-smoke-')

    def cleanup():
        for attempt in range(10):
            try:
                shutil.rmtree(directory)
                return
            except OSError:
                if attempt == 9:
                    raise
                time.sleep(.3)

    try:
        yield directory
    except BaseException as original:
        try:
            cleanup()
        except OSError as error:
            original.add_note(f'Could not remove temporary smoke folder {directory}: {error}')
        raise
    else:
        cleanup()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lut-archive', type=Path,
                        help='Existing official Fuji ZIP; its LUT hashes are still verified')
    args = parser.parse_args(argv)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with smoke_workspace() as temporary:
        # A moved installation, Unicode paths and an unrelated working directory
        # expose dependencies accidentally taken from the developer checkout.
        directory = Path(temporary) / 'Photos été 日本'
        directory.mkdir()
        portable = Path(temporary) / 'KŌRA portable'
        shutil.copytree(ROOT / 'dist/windows/Kora', portable)
        app = portable / 'Kora.exe'
        environment = {key: value for key, value in os.environ.items()
                       if key not in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV')}
        with managed_app(app, '--no-browser', '--port', port, '--root', directory,
                         cwd=temporary, env=environment) as process:
            base = f'http://127.0.0.1:{port}'
            for attempt in range(60):
                if process.poll() is not None:
                    raise RuntimeError(f'Packaged app exited: {process.returncode}')
                try:
                    with urlopen(base, timeout=1) as response:
                        page = response.read().decode('utf-8')
                    break
                except OSError:
                    time.sleep(.5)
            else:
                raise RuntimeError('Packaged app did not start within 30 seconds')
            assert '<title>KŌRA</title>' in page
            for asset in ('app.js', 'style.css', 'kora.css', 'diagnostics.js', 'viewer.js'):
                with urlopen(base + '/' + asset, timeout=5) as response:
                    assert len(response.read()) > 100
            print(json.dumps({'packaged_server': 'ok', 'assets': 'ok'}))
        report = Path(directory) / 'ui-report.json'
        with urlopen(RAW_URL, timeout=60) as response:
            sample = response.read()
        assert hashlib.sha256(sample).hexdigest() == RAW_SHA256, 'RAW sample checksum changed'
        (Path(directory) / 'sample.CR2').write_bytes(sample)
        # Exercise the normal first-run LUT installation without redistributing
        # vendor files: the complete pack and extracted tables stay temporary.
        lut_archive = Path(directory) / 'fuji-luts.zip'
        if args.lut_archive:
            shutil.copyfile(args.lut_archive, lut_archive)
        else:
            with urlopen(MANIFEST['source'], timeout=120) as response:
                lut_archive.write_bytes(response.read())
        lut_directory = install_archive(lut_archive, Path(directory) / 'luts')
        with managed_app(app, '--root', directory, '--smoke-report', report,
                         cwd=temporary, env={**environment, 'KORA_LUT_DIR': str(lut_directory)}) as process:
            code = process.wait(timeout=240)
            if code:
                raise subprocess.CalledProcessError(code, process.args)
        result = json.loads(report.read_text(encoding='utf-8'))
        status = studio_status()
        assert {key: result[key] for key in ('title', 'films', 'grid')} == {
            'title': 'KŌRA', 'films': expected_films(status), 'grid': True}, result
        assert 'kodachrome64' in result['raw']['previews'], result
        assert result['raw']['export'] == [1944, 1296], result
        assert result['raw']['icc'], result
        print('Packaged WebView2 UI, RAW previews, source-detail tile and JPEG export: OK')
        print(json.dumps(result['raw']))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        log = diagnostics.log_path()
        if log.is_file():
            print('Packaged application diagnostics:', flush=True)
            print(log.read_text(encoding='utf-8')[-16000:], flush=True)
        raise
