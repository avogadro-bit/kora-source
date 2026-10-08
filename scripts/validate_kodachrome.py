"""Compare the runtime to full constrained spectra and spectral integration.

--write-reference regenerates the small deterministic test fixture, using the
reference code and source data, never the runtime interpolation tables.
"""
from pathlib import Path
import argparse
import json
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
FIXTURE=ROOT/'tests/data/kodachrome_reference.json'


def reference():
    sys.path.insert(0,str(ROOT/'scripts/kodachrome_reference'))
    from k64_reconstruction import ReconstructionBench
    from k64_observation import ObservationRenderer
    from k64_dng import encode_srgb
    bench=ReconstructionBench('zero')
    viewer=ObservationRenderer(bench.film,'D50')
    rng=np.random.default_rng(64042)
    gray=np.geomspace(1e-6,1,24)
    cube=np.stack(np.meshgrid([0.,1.],[0.,1.],[0.,1.],indexing='ij'),-1).reshape(-1,3)
    rgb=np.vstack((np.repeat(gray[:,None],3,axis=1),cube,rng.uniform(0,1,(64,3)),rng.uniform(0,1,(64,3))**2.4))
    responses=np.array([bench.responses(bench.reconstruct(c,'pente')[0]) for c in rgb])
    responses=np.clip(responses,0,1)
    exposures=[-3.,-1.,-.5,0.,.5,1.,3.]
    outputs=[encode_srgb(viewer.integrate(bench.film.amounts_for_rgb(responses,ev+.5))).tolist() for ev in exposures]
    return {'source':'Full constrained pente solve and direct spectral integration; no runtime table.',
            'seed':64042,'base_ev':.5,'rgb':rgb.tolist(),'exposures':exposures,'display_srgb':outputs}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--write-reference',action='store_true');args=parser.parse_args()
    if args.write_reference:
        FIXTURE.parent.mkdir(exist_ok=True)
        FIXTURE.write_text(json.dumps(reference(),indent=2)+'\n')
        print(f'Wrote {FIXTURE.name}')
        return
    from kora.kodachrome import apply_kodachrome
    fixture=json.loads(FIXTURE.read_text());rgb=np.asarray(fixture['rgb'])[:,None,:]
    reports=[]
    for ev,truth in zip(fixture['exposures'],fixture['display_srgb']):
        quick=apply_kodachrome(rgb*2**ev,ev,workers=1)[:,0]
        error=np.abs(quick-np.asarray(truth))
        reports.append({'ev':ev,'max_channel_error':float(error.max()),'p99_channel_error':float(np.percentile(error,99))})
    print(json.dumps({'pixels_per_exposure':len(rgb),'exposures':reports},indent=2))
    if max(r['max_channel_error'] for r in reports)>.005:
        raise SystemExit('Interpolation error exceeds the validation threshold.')


if __name__=='__main__':main()
