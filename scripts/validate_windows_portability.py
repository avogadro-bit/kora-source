"""Check a built Kora Windows folder on a real Windows machine, without downloads.

Uses only Python's standard library, not an installed Kora environment. Example:
    py scripts/validate_windows_portability.py --app dist/windows/Kora/Kora.exe \
        --report build/windows-portability.json

Pass --raw with one local RAW and --lut-dir with the installed Fuji LUT folder
to also check previews, a source-detail tile and an export. The RAW is copied to
a temporary Unicode path; the original is never opened by Kora or changed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def pe_architecture(path):
    """Read the COFF machine field, without executing an unverified binary."""
    with path.open('rb') as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b'MZ':
            raise ValueError('Application does not have a Windows PE header')
        offset = struct.unpack_from('<I', header, 60)[0]
        stream.seek(offset)
        header = stream.read(6)
        if len(header) != 6 or header[:4] != b'PE\0\0':
            raise ValueError('Application PE signature is invalid')
        machine = struct.unpack_from('<H', header, 4)[0]
    return {0x14c: 'x86', 0x8664: 'x86_64', 0xaa64: 'arm64'}.get(machine, hex(machine))


def environment():
    result = {
        'system': platform.system(), 'release': platform.release(),
        'version': platform.version(), 'machine': platform.machine(),
        'process_architecture': pe_architecture(Path(sys.executable)) if sys.platform == 'win32' else platform.machine(),
        'pointer_bits': struct.calcsize('P') * 8,
        'python': platform.python_version(),
        # These inherited variables can describe the emulation environment,
        # so keep them separate from the OS machine and the Python PE header.
        'environment_architecture': os.environ.get('PROCESSOR_ARCHITEW6432',
                                                  os.environ.get('PROCESSOR_ARCHITECTURE')),
    }
    if sys.platform == 'win32':
        version = sys.getwindowsversion()
        result['windows_build'] = version.build
    return result


def unused_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def stop_own_process(process):
    if process.poll() is None:
        if sys.platform == 'win32':
            # The PyInstaller windowed bootloader can own a worker process.
            # Stopping only the parent leaves its server and DLLs alive.
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=False, timeout=15)
        else:
            process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def check_server(app, directory, child_env, timeout):
    port = unused_port()
    start = time.perf_counter()
    process = subprocess.Popen(
        [str(app), '--no-browser', '--port', str(port), '--root', str(directory)],
        env=child_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f'http://127.0.0.1:{port}'
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f'Packaged server exited with code {process.returncode}')
            try:
                with urlopen(base, timeout=1) as response:
                    page = response.read().decode('utf-8')
                break
            except OSError:
                time.sleep(.2)
        else:
            raise TimeoutError(f'Packaged server did not start within {timeout:g} seconds')
        startup = time.perf_counter() - start
        if '<title>KŌRA</title>' not in page:
            raise RuntimeError('Wrong or truncated application HTML')
        assets = {}
        for name in ('app.js', 'viewer.js', 'style.css', 'kora.css', 'diagnostics.js'):
            with urlopen(base + '/' + name, timeout=10) as response:
                data = response.read()
            if len(data) < 100:
                raise RuntimeError(f'Empty application asset: {name}')
            assets[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        return {'status': 'passed', 'startup_seconds': round(startup, 3), 'assets': assets}
    finally:
        stop_own_process(process)


def check_window(app, directory, child_env, timeout, with_raw):
    target = directory.parent / 'résultat-interface.json'
    start = time.perf_counter()
    process = subprocess.Popen(
        [str(app), '--port', str(unused_port()), '--root', str(directory),
         '--smoke-report', str(target)], env=child_env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        code = process.wait(timeout=timeout)
        if code != 0 or not target.is_file():
            raise RuntimeError(f'Window smoke check failed (exit {code}, report {target.is_file()})')
        result = json.loads(target.read_text(encoding='utf-8'))
        if result.get('title') != 'KŌRA' or not result.get('grid'):
            raise RuntimeError('The WebView2 smoke report did not confirm the interface')
        if 'kodachrome64' not in result.get('films', []):
            raise RuntimeError('Kodachrome 64 is missing from the packaged film list')
        if with_raw and not result.get('raw'):
            raise RuntimeError('The supplied RAW was not exercised by the application')
        return {'status': 'passed', 'elapsed_seconds': round(time.perf_counter() - start, 3),
                'raw_test_requested': with_raw, 'result': result}
    finally:
        stop_own_process(process)


def validate(args):
    app = args.app.resolve(strict=True)
    result = {'schema': 1, 'environment': environment(),
              'application': {'filename': app.name, 'sha256': sha256(app)},
              'status': 'failed'}
    try:
        result['application']['architecture'] = pe_architecture(app)
        if sys.platform != 'win32':
            result.update(status='not_run', reason='Runtime checks require a real Windows session')
            return result
        if args.raw is not None and not args.raw.is_file():
            raise ValueError('--raw must be an existing, locally available RAW file')
        if args.raw is not None:
            flags = getattr(args.raw.stat(), 'st_file_attributes', 0)
            if flags & (0x1000 | 0x40000 | 0x400000):  # OFFLINE / RECALL_ON_OPEN / RECALL_ON_DATA_ACCESS
                raise ValueError('Download the RAW locally before testing; cloud placeholders are skipped')
        with tempfile.TemporaryDirectory(prefix='kora-portabilité-') as temporary:
            directory = Path(temporary)
            photos = directory / 'photographies échantillon'
            photos.mkdir()
            if args.raw is not None:
                shutil.copyfile(args.raw, photos / ('échantillon' + args.raw.suffix))
            local_data = directory / 'application-data'
            local_data.mkdir()
            child_env = {**os.environ, 'LOCALAPPDATA': str(local_data),
                         'KORA_NO_BROWSER': '0', 'FILM_RECIPE_LAB_NO_BROWSER': '0'}
            if args.lut_dir is not None:
                child_env['KORA_LUT_DIR'] = str(args.lut_dir.resolve(strict=True))
            result['server'] = check_server(app, photos, child_env, args.timeout)
            try:
                result['window'] = check_window(app, photos, child_env, args.timeout, args.raw is not None)
            finally:
                # Kora's own bounded diagnostics redact paths and session tokens.
                log = local_data / 'Kora/Logs/errors.jsonl'
                if log.is_file():
                    result['application_diagnostics'] = log.read_text(encoding='utf-8')[-16000:]
        result['status'] = 'passed'
    except Exception as exc:
        result['error'] = f'{type(exc).__name__}: {exc}'
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True, help='Packaged Kora.exe')
    parser.add_argument('--report', type=Path, required=True, help='Local JSON output')
    parser.add_argument('--raw', type=Path, help='One locally available RAW; never modified')
    parser.add_argument('--lut-dir', type=Path, help='Existing Fuji LUT folder, for the RAW checks')
    parser.add_argument('--timeout', type=float, default=240, help='Seconds per stage (default 240)')
    args = parser.parse_args(argv)
    if not args.app.is_file():
        parser.error('--app must point to an existing Kora.exe')
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    result = validate(args)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'report': str(args.report)}, ensure_ascii=False))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
