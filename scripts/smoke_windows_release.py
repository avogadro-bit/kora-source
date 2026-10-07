"""Start the packaged server, verify its assets/API, then stop our own process."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from urllib.request import urlopen

from kora import diagnostics
from kora.studio import studio_status
from kora.lut_install import install_archive
from kora.official_luts import MANIFEST

ROOT = Path(__file__).resolve().parents[1]

# Public regression sample from rawpy / rawsamples.ch, CC BY-NC-SA 4.0.
# Downloaded into the temporary test directory; never bundled with Kora.
RAW_URL = ('https://raw.githubusercontent.com/letmaik/rawpy/'
           'a39c2e7a44911889c3360891012f862f904ba551/test/RAW_CANON_40D_SRAW_V103.CR2')
RAW_SHA256 = '152382ce4dbf644899d12b41b4c577f07638aa3ec5745ac344c36bad93826125'


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='kora-smoke-') as directory:
        app = ROOT / 'dist/windows/Kora/Kora.exe'
        process = subprocess.Popen([str(app), '--no-browser', '--port', str(port), '--root', directory])
        try:
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
            for asset in ('app.js', 'style.css', 'kora.css', 'diagnostics.js'):
                with urlopen(base + '/' + asset, timeout=5) as response:
                    assert len(response.read()) > 100
            print(json.dumps({'packaged_server': 'ok', 'assets': 'ok'}))
        finally:
            process.terminate()
            process.wait(timeout=15)
        report = Path(directory) / 'ui-report.json'
        with urlopen(RAW_URL, timeout=60) as response:
            sample = response.read()
        assert hashlib.sha256(sample).hexdigest() == RAW_SHA256, 'RAW sample checksum changed'
        (Path(directory) / 'sample.CR2').write_bytes(sample)
        # Exercise the normal first-run LUT installation without redistributing
        # vendor files: the complete pack and extracted tables stay temporary.
        lut_archive = Path(directory) / 'fuji-luts.zip'
        with urlopen(MANIFEST['source'], timeout=120) as response:
            lut_archive.write_bytes(response.read())
        lut_directory = install_archive(lut_archive, Path(directory) / 'luts')
        subprocess.run([str(app), '--root', directory, '--smoke-report', str(report)],
                       env={**os.environ, 'KORA_LUT_DIR': str(lut_directory)},
                       check=True, timeout=240)
        result = json.loads(report.read_text(encoding='utf-8'))
        status = studio_status()
        expected_films = sorted(set(status['official_lut_films']) |
                                set(status['xm5_reference_validation']['films']))
        assert {key: result[key] for key in ('title', 'films', 'grid')} == {
            'title': 'KŌRA', 'films': expected_films, 'grid': True}, result
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
