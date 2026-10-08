"""Bake the documented E-88 model; no photograph or fitted image pixels enter it.

Run with OPENBLAS_NUM_THREADS=1 for reproducible small constrained solves.
The reference modules/data are retained verbatim from the standalone study.
"""
from pathlib import Path
import hashlib
import json
import sys
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = Path(__file__).with_name('kodachrome_reference')
sys.path.insert(0, str(REFERENCE))
from k64_reconstruction import ReconstructionBench
from k64_observation import ObservationRenderer


def main():
    start = time.perf_counter()
    bench = ReconstructionBench('zero')
    n = 65
    code = np.linspace(0, 1, n)
    axis = np.where(code <= .04045, code/12.92, ((code+.055)/1.055)**2.4)
    grid = np.stack(np.meshgrid(axis, axis, axis, indexing='ij'), axis=-1).reshape(-1, 3)
    q, a = bench.quadratics['pente'], bench.rgb_operator
    prior = np.ones((len(bench.knots), 1))*np.array([.2126,.7152,.0722])
    inverse_a = np.linalg.solve(q, a.T)
    linear = prior + inverse_a @ np.linalg.solve(a@inverse_a, np.eye(3)-a@prior)
    responses = np.empty_like(grid)
    bounded = []
    for begin in range(0, len(grid), 4096):
        block = grid[begin:begin+4096]
        reflectance = block@linear.T
        good = np.all((reflectance >= -1e-10) & (reflectance <= 1+1e-10), axis=-1)
        responses[begin:begin+len(block)][good] = block[good]@(bench.film_operator@linear).T
        bounded.extend((np.flatnonzero(~good)+begin).tolist())
    print(f'{len(grid)} nodes; {len(bounded)} bounded spectral solves.', flush=True)
    for j, index in enumerate(bounded):
        r, _ = bench.reconstruct(grid[index], 'pente')
        responses[index] = bench.responses(r)
        if (j+1)%2000 == 0:
            print(f'{j+1}/{len(bounded)} constrained nodes; {time.perf_counter()-start:.1f} s', flush=True)
    if not np.isfinite(responses).all() or responses.min() < -1e-9 or responses.max() > 1+1e-9:
        raise RuntimeError('Invalid layer-response table.')
    film = bench.film
    viewer = ObservationRenderer(film, 'D50')
    check = viewer.build_lut(65)
    if check['max_abs_encoded_srgb_error'] > .005:
        raise RuntimeError('Dye-table precision check failed.')
    out = ROOT/'kora/film_data'
    out.mkdir(exist_ok=True)
    asset = out/'kodachrome64_v1.npz'
    np.savez_compressed(asset, response_axis=axis.astype(np.float64),
                        responses=np.clip(responses,0,1).reshape(n,n,n,3).astype(np.float32),
                        logh=film.logh, amounts=film.amounts, anchor=np.array(film.anchor),
                        dye_rgb=viewer.lut, dye_max=viewer.lut_max)
    manifest = {'version':1, 'film':'kodachrome64', 'label':'Kodachrome 64 · Experimental',
                'sha256':hashlib.sha256(asset.read_bytes()).hexdigest(),
                'method':'minimum first-derivative quadratic (pente)',
                'scene_illuminant':'D65', 'viewing_illuminant':'D50',
                'observation_adaptation':'full Bradford of lamp white to sRGB D65',
                'base_ev':0.5, 'sensitivity_tails':'zero', 'dye_tails':'hold',
                'response_grid':n, 'response_interpolation':'tetrahedral in linear RGB',
                'dye_grid':65, 'dye_lut_check':check,
                'reference_files_sha256':{str(p.relative_to(REFERENCE)):hashlib.sha256(p.read_bytes()).hexdigest()
                                          for p in sorted(REFERENCE.rglob('*'))
                                          if p.is_file() and '__pycache__' not in p.parts},
                'elapsed_seconds':time.perf_counter()-start,
                'limitations':['Digitized Kodak E-88 plots, not original Kodak measurements.',
                               'Hypothetical RGB-to-reflectance reconstruction, not measured scene spectra.',
                               'Base EV is conventional, not calibrated film or camera exposure.',
                               'CIE-derived tables: CC BY-SA 4.0; see source attributions.',
                               'Not a Kodak product, not a native Fuji film simulation.']}
    (out/'kodachrome64_v1.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'Written {asset}: {asset.stat().st_size} bytes, {manifest["elapsed_seconds"]:.1f} s',flush=True)


if __name__ == '__main__':
    main()
