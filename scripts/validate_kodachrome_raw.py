"""Local, read-only RAW validation. Outputs are written only to --output."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import time
import numpy as np
from PIL import Image
import tifffile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'scripts/kodachrome_reference'))
from kora.studio import decode, render, encode, StudioRecipe, resize_float
from kora.kodachrome import load_model
from k64_reconstruction import ReconstructionBench
from k64_observation import ObservationRenderer
from k64_dng import encode_srgb


def main():
    parser=argparse.ArgumentParser();parser.add_argument('raw',type=Path)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--full',action='store_true')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    before=hashlib.file_digest(args.raw.open('rb'),'sha256').hexdigest()
    start=time.perf_counter();linear=decode(args.raw,preview=not args.full);decode_seconds=time.perf_counter()-start
    recipe=StudioRecipe(film='kodachrome64',file_type='tiff16',name='Kodachrome 64 — Experimental')
    start=time.perf_counter();result=render(linear,recipe);render_seconds=time.perf_counter()-start
    # Selected samples are checked through the full direct spectral model.
    flat=linear.reshape(-1,3);indices=np.random.default_rng(64042).choice(len(flat),192,replace=False)
    samples=np.maximum(flat[indices].astype(float),0)
    intensity=np.maximum(samples.max(axis=1,keepdims=True),1.)
    reflectance_rgb=samples/intensity
    bench=ReconstructionBench('zero');viewer=ObservationRenderer(bench.film,'D50')
    response=np.clip(np.array([bench.responses(bench.reconstruct(c,'pente')[0]) for c in reflectance_rgb]),0,1)*intensity
    h=bench.film.anchor+np.log10(np.maximum(response,1e-30)/.18)+.5*np.log10(2)
    amounts=np.column_stack([np.interp(h[:,c],bench.film.logh,bench.film.amounts[:,c]) for c in range(3)])
    truth=encode_srgb(viewer.integrate(amounts))
    error=np.abs(result.reshape(-1,3)[indices]-truth)
    y,x=linear.shape[0]//3,linear.shape[1]//3
    tile=render(linear[y:y+192,x:x+192],recipe,output_transform=False,origin=(y,x))
    tile_error=float(np.max(np.abs(tile-result[y:y+192,x:x+192])))
    data,mime=encode(result,recipe)
    target=args.output/(args.raw.stem+'_Kodachrome64.tiff');target.write_bytes(data)
    with tifffile.TiffFile(target) as f:
        assert f.asarray().dtype==np.uint16 and f.asarray().shape==result.shape
        assert json.loads(f.pages[0].description)['experimental']
    small=resize_float(result,1400)
    jpeg,_=encode(small,recipe.model_copy(update={'file_type':'jpeg'}))
    (args.output/(args.raw.stem+'_Kodachrome64.jpg')).write_bytes(jpeg)
    after=hashlib.file_digest(args.raw.open('rb'),'sha256').hexdigest()
    report={'photo':args.raw.name,'sha256_before':before,'sha256_after':after,'source_unchanged':before==after,
            'model_sha256':load_model()[1]['sha256'],'shape':list(result.shape),'decode_seconds':decode_seconds,
            'render_seconds':render_seconds,'exact_reference_samples':len(indices),
            'max_channel_error':float(error.max()),'p99_channel_error':float(np.percentile(error,99)),
            'tile_max_error':tile_error,'tiff_bytes':len(data),'all_pixels_finite':bool(np.isfinite(result).all()),
            'negative_input_pixel_fraction':float(np.mean(np.any(linear<0,axis=2))),
            'hdr_input_pixel_fraction':float(np.mean(np.any(linear>1,axis=2))),
            'scope':'Agreement with the direct model at the same Kora input, including the documented HDR extension; not film accuracy.'}
    (args.output/(args.raw.stem+'_validation.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)
    assert before==after and tile_error==0 and error.max()<.005


if __name__=='__main__':main()
