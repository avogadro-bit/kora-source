"""Exercise a relocated frozen Mac app, without Fuji LUTs or a GUI window.

Requires Pillow in the test runner. The packaged app uses only its own runtime.
The input RAW is copied to a temporary Unicode path and is never modified.
"""
import argparse
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import tempfile
import time
from urllib.request import Request, urlopen

from PIL import Image


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check_image(data, expected=None, icc=False):
    with Image.open(BytesIO(data)) as image:
        image.load()
        if image.format != 'JPEG' or min(image.size) < 128:
            raise RuntimeError('Invalid rendered JPEG')
        if expected is not None and list(image.size) != expected:
            raise RuntimeError(f'Unexpected dimensions: {image.size}, expected {expected}')
        if icc and not image.info.get('icc_profile'):
            raise RuntimeError('Export has no ICC profile')
        return {'dimensions': list(image.size), 'bytes': len(data),
                'icc': bool(image.info.get('icc_profile')),
                'sha256': hashlib.sha256(data).hexdigest()}


def validate(args):
    source = args.raw.resolve(strict=True)
    if getattr(source.stat(), 'st_flags', 0) & 0x40000000:
        raise ValueError('Download the RAW locally before testing')
    before = digest(source)
    report = {'status': 'failed', 'system': platform.platform(),
              'host_architecture': platform.machine(), 'raw_sha256': before,
              'scope': 'Relocated packaged server, assets, K64 preview/tile/export; not a native-window or oldest-OS test.'}
    with tempfile.TemporaryDirectory(prefix='kora-mac-smoke-') as temporary:
        root = Path(temporary)
        app = root / 'Application déplacée 日本' / 'KŌRA.app'
        shutil.copytree(args.app.resolve(strict=True), app, symlinks=True)
        photos = root / 'Photos été 日本'
        photos.mkdir()
        shutil.copyfile(source, photos / ('échantillon' + source.suffix))
        lut_dir = root / 'empty-luts'
        lut_dir.mkdir()
        child_env = {key: value for key, value in os.environ.items()
                     if key not in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV')}
        child_env['KORA_LUT_DIR'] = str(lut_dir)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        started = time.perf_counter()
        log_path = root / 'server.log'
        with log_path.open('wb') as log:
            process = subprocess.Popen([str(app / 'Contents/MacOS/Kora'), '--no-browser',
                                        '--port', str(port), '--root', str(photos)],
                                       cwd=root, env=child_env, stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    match = re.search(r'(http://127\.0\.0\.1:\d+)/#session=([\w-]+)',
                                      log_path.read_text(encoding='utf-8', errors='replace'))
                    if match:
                        base, token = match.groups()
                        break
                    if process.poll() is not None:
                        raise RuntimeError(f'Packaged application exited: {process.returncode}')
                    time.sleep(.2)
                else:
                    raise TimeoutError('Packaged application did not start within 90 seconds')

                def request(route, payload=None):
                    body = None if payload is None else json.dumps(payload).encode('utf-8')
                    headers = {'X-Fuji-Session': token, 'Content-Type': 'application/json'}
                    with urlopen(Request(base + route, data=body, headers=headers), timeout=300) as response:
                        return response.read()

                library = json.loads(request('/api/library'))
                report.update(version=library['version'], startup_seconds=time.perf_counter()-started)
                if 'kodachrome64' not in library['engine'].get('special_films', {}):
                    raise RuntimeError('Packaged Kodachrome film missing')
                report['assets'] = {}
                for name in ('app.js', 'viewer.js', 'style.css', 'kora.css', 'diagnostics.js'):
                    data = request('/' + name)
                    if len(data) < 100:
                        raise RuntimeError(f'Missing static asset: {name}')
                    report['assets'][name] = hashlib.sha256(data).hexdigest()
                listing = json.loads(request('/api/folder', {'path': str(photos), 'recursive': False}))
                if len(listing['files']) != 1:
                    raise RuntimeError('Unicode RAW path was not discovered')
                payload = {'id': listing['files'][0]['id'], 'recipe': {'film': 'kodachrome64'},
                           'quality': 'display', 'edge': 1400}
                report['preview'] = check_image(request('/api/render', payload))
                report['tile'] = check_image(request('/api/tile',
                    {'id': payload['id'], 'recipe': payload['recipe'], 'x': 0, 'y': 0, 'size': 512, 'level': 1}),
                    expected=[512, 512])
                report['export'] = check_image(request('/api/export', payload), expected=args.expected_size, icc=True)
                report['without_fuji_luts'] = not any(lut_dir.iterdir())
                report['source_unchanged'] = digest(source) == before
                if not report['source_unchanged']:
                    raise RuntimeError('Source RAW changed during test')
                report['status'] = 'passed'
            finally:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--expected-size', type=int, nargs=2, metavar=('WIDTH', 'HEIGHT'))
    args = parser.parse_args()
    try:
        report = validate(args)
    except Exception as exc:
        report = {'status': 'failed', 'error': f'{type(exc).__name__}: {exc}'}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
