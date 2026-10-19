"""Compare KŌRA's RAW decoding with two rawpy builds, bit for bit.

Each build runs in its own process (only one rawpy can be imported at once).
For every RAW, the full-resolution and preview linear buffers produced by
kora.studio.decode are hashed; files that differ are compared numerically.
The candidate build is decoded twice to detect non-deterministic output.

    .venv-macos-release/bin/python scripts/compare_rawpy_builds.py \
        --candidate /path/to/site-packages-with-openmp-rawpy PHOTO.RAF PHOTO.DNG ...
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def worker(photos, save_dir=None, compare_dir=None):
    sys.path.insert(0, str(ROOT))
    import numpy as np
    import rawpy
    from kora.studio import decode, _preview_source
    results = []
    for photo in photos:
        _preview_source.cache_clear()
        record = {'photo': photo, 'rawpy': rawpy.__file__, 'openmp': rawpy.flags.get('OPENMP')}
        try:
            started = time.perf_counter()
            full = np.ascontiguousarray(decode(Path(photo), preview=False))
            record['full_seconds'] = time.perf_counter() - started
            preview = np.ascontiguousarray(decode(Path(photo), preview=True))
        except Exception as exc:  # Unsupported files must fail identically in both builds.
            record['error'] = f'{type(exc).__name__}: {exc}'
            results.append(record)
            continue
        record['shape'] = list(full.shape)
        record['full_sha256'] = hashlib.sha256(full.tobytes()).hexdigest()
        record['preview_sha256'] = hashlib.sha256(preview.tobytes()).hexdigest()
        key = hashlib.sha256(photo.encode()).hexdigest()[:16]
        if save_dir:
            np.save(Path(save_dir)/f'{key}.npy', full)
        if compare_dir:
            reference = np.load(Path(compare_dir)/f'{key}.npy')
            difference = np.abs(full.astype(np.float64) - reference)
            changed = np.any(full != reference, axis=-1)
            record['max_abs_diff'] = float(difference.max())
            record['mean_abs_diff'] = float(difference.mean())
            record['changed_pixel_fraction'] = float(changed.mean())
            # Express the difference in 8-bit display steps of the linear buffer.
            record['max_abs_diff_8bit_linear'] = float(difference.max()*255)
        results.append(record)
    print(json.dumps(results))


def run_worker(python, site, photos, **options):
    environment = {**os.environ, 'PYTHONPATH': site or ''}
    command = [python, __file__, '--worker', *photos]
    for name, value in options.items():
        if value:
            command += [f'--{name.replace("_", "-")}', str(value)]
    completed = subprocess.run(command, env=environment, capture_output=True, text=True, check=True)
    return {item['photo']: item for item in json.loads(completed.stdout.strip().splitlines()[-1])}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('photos', nargs='+')
    parser.add_argument('--candidate', help='directory placed first on PYTHONPATH for the candidate rawpy')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--save-dir', help=argparse.SUPPRESS)
    parser.add_argument('--compare-dir', help=argparse.SUPPRESS)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.worker:
        return worker(args.photos, args.save_dir, args.compare_dir)
    if not args.candidate:
        parser.error('--candidate is required')
    photos = [str(Path(p).resolve()) for p in args.photos]
    python = sys.executable
    stock = run_worker(python, None, photos)
    first = run_worker(python, args.candidate, photos)
    second = run_worker(python, args.candidate, photos)
    report = []
    for photo in photos:
        a, b, c = stock[photo], first[photo], second[photo]
        row = {'photo': Path(photo).name, 'stock_openmp': a['openmp'], 'candidate_openmp': b['openmp']}
        if 'error' in a or 'error' in b:
            row.update(stock_error=a.get('error'), candidate_error=b.get('error'),
                       same_outcome=a.get('error') == b.get('error'))
        else:
            row.update(megapixels=round(a['shape'][0]*a['shape'][1]/1e6, 1),
                       stock_seconds=round(a['full_seconds'], 2), candidate_seconds=round(b['full_seconds'], 2),
                       speedup=round(a['full_seconds']/b['full_seconds'], 2),
                       full_identical=a['full_sha256'] == b['full_sha256'],
                       preview_identical=a['preview_sha256'] == b['preview_sha256'],
                       candidate_deterministic=(b['full_sha256'] == c['full_sha256']
                                                and b['preview_sha256'] == c['preview_sha256']))
        report.append(row)
        print(json.dumps(row), flush=True)
    differing = [str(Path(p)) for p, r in zip(photos, report) if r.get('full_identical') is False]
    if differing:
        with tempfile.TemporaryDirectory(prefix='kora-rawpy-') as scratch:
            run_worker(python, None, differing, save_dir=scratch)
            details = run_worker(python, args.candidate, differing, compare_dir=scratch)
        for row in report:
            match = next((d for p, d in details.items() if Path(p).name == row['photo']), None)
            if match:
                row.update({k: match[k] for k in ('max_abs_diff', 'mean_abs_diff', 'changed_pixel_fraction',
                                                  'max_abs_diff_8bit_linear')})
                print(json.dumps({'photo': row['photo'], **{k: row[k] for k in ('max_abs_diff', 'mean_abs_diff',
                      'changed_pixel_fraction')}}), flush=True)
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
