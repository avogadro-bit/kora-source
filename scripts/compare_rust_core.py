"""Compare the Rust kora-core LUT adapter with kora/official_luts.py.

Decodes each RAW with the normal full-resolution KORA decoder, applies the same
official film in Python and in Rust, then reports timing and pixel differences.

    cargo build --release --manifest-path rust/Cargo.toml
    .venv/bin/python scripts/compare_rust_core.py PHOTO.RAF [PHOTO.DNG ...] --film provia
"""
from pathlib import Path
import argparse
import json
import subprocess
import sys
import tempfile
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kora.official_luts import apply_official, lut_path  # noqa: E402
from kora.studio import decode  # noqa: E402


def best_of(repeats, callback):
    best, result = float('inf'), None
    for _ in range(repeats):
        started = time.perf_counter()
        result = callback()
        best = min(best, time.perf_counter() - started)
    return best, result


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('photos', nargs='+', type=Path)
    parser.add_argument('--film', default='provia')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--bench', type=Path, default=ROOT/'rust'/'target'/'release'/'kora-bench')
    args = parser.parse_args()
    if not args.bench.is_file():
        parser.error(f'{args.bench} is missing; build it with cargo build --release --manifest-path rust/Cargo.toml')
    reports = []
    with tempfile.TemporaryDirectory(prefix='kora-rust-') as scratch:
        scratch = Path(scratch)
        for photo in args.photos:
            linear = np.ascontiguousarray(decode(photo, preview=False), dtype=np.float32)
            python_seconds, expected = best_of(args.repeats, lambda: apply_official(linear, args.film))
            source, output = scratch/'linear.npy', scratch/'rust.npy'
            np.save(source, linear)
            completed = subprocess.run([str(args.bench), str(lut_path(args.film)), str(source), str(output),
                                        str(args.repeats)], capture_output=True, text=True, check=True)
            rust = json.loads(completed.stdout)
            difference = np.abs(np.load(output) - expected) * 255
            reports.append({
                'photo': photo.name, 'film': args.film,
                'megapixels': round(linear.shape[0]*linear.shape[1]/1e6, 1),
                'python_seconds': round(python_seconds, 3),
                'rust_seconds': rust['apply_seconds'],
                'speedup': round(python_seconds/rust['apply_seconds'], 1),
                'rust_threads': rust['threads'],
                'mean_abs_diff_8bit': float(difference.mean()),
                'max_abs_diff_8bit': float(difference.max()),
                'pixels_differing_8bit': float(np.mean(np.any(
                    np.rint(np.load(output)*255) != np.rint(expected*255), axis=-1))),
            })
            print(json.dumps(reports[-1]), flush=True)
    return reports


if __name__ == '__main__':
    main()
