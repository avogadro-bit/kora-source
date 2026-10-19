"""Unmodified Fujifilm video LUTs with an explicit photographic input adapter.

F-Log2 formula and F-Gamut primaries: Fujifilm data sheet v1.1.
Output viewing: Rec.709 / D65 / gamma 2.2, per GFX ETERNA 55 White Paper
v1.01 page 13, converted to sRGB for browser/ICC exports. Not a photo ISP.
"""
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import os
import sys
from .platform_support import windows_data_directory
from .compatibility import lut_directory, lut_override
import numpy as np
from scipy.ndimage import map_coordinates

ROOT = Path(__file__).with_name('luts')
MANIFEST = json.loads((ROOT/'manifest.json').read_text())
FILMS = tuple(MANIFEST['files'])
LUT_DISPLAY_GAMMA = 2.2


def user_lut_directory():
    default = windows_data_directory() / 'luts' if sys.platform == 'win32' else lut_directory()
    override = lut_override()
    return Path(override if override is not None else default).expanduser()


def lut_path(film):
    name=MANIFEST['files'][film]['file']
    user_path=user_lut_directory()/name
    # An explicit override is isolated (useful for portable installations/tests).
    if lut_override() is not None or user_path.is_file():
        return user_path
    return ROOT/name  # Existing development installations remain compatible.


def missing_luts():
    return [film for film in FILMS if not lut_path(film).is_file()]
# Linear sRGB / BT.709 D65 to F-Gamut (BT.2020 primaries), row vectors.
TO_F_GAMUT = np.array([[.627403896,.069097289,.016391439],
                      [.329283038,.919540395,.088013308],
                      [.043313066,.011362316,.895595253]],np.float32)


def flog2_encode(reflection):
    x=np.maximum(reflection,0)
    return np.where(x < .000889,8.799461*x+.092864,
                    .245281*np.log10(5.555556*x+.064829)+.384316)


class MissingLUTError(ValueError):
    """The optional external Fuji LUT is not installed."""


@lru_cache(maxsize=10)
def load_lut(film):
    info=MANIFEST['files'][film]
    path=lut_path(film)
    if not path.is_file():
        raise MissingLUTError('Fuji LUT missing. Download the GFX ETERNA 55 v1.10 ZIP from Fuji, then run: python -m kora.lut_install path/archive.zip')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=info['sha256']:
        raise ValueError(f'Official LUT has been modified: {film}')
    lines=raw.decode().splitlines()
    if 'LUT_3D_SIZE 65' not in lines:
        raise ValueError('Grille LUT inattendue')
    values=np.loadtxt([s for s in lines if s.strip() and not s.startswith(('#','LUT_'))],dtype=np.float32)
    if values.shape!=(65**3,3) or not np.isfinite(values).all():
        raise ValueError('Invalid official LUT')
    # .cube enumerates red fastest, then green, then blue.
    table=values.reshape(65,65,65,3)
    table.setflags(write=False)
    return table


def interpolate(table,rgb):
    coords=np.moveaxis(np.clip(rgb,0,1)*64,-1,0)[::-1]
    return np.stack([map_coordinates(table[...,c],coords,order=1,
                     mode='nearest',prefilter=False) for c in range(3)],axis=-1)


def lut_worker_count(cpu_count=None):
    """Use several performance cores without oversubscribing image batches."""
    cpu_count=max(1,int(cpu_count or os.cpu_count() or 1))
    return min(10,max(1,(cpu_count*3+3)//4))


@lru_cache(maxsize=4)
def render_executor(workers):
    # One shared pool caps total pixel concurrency even when several photographs
    # are exported at once. NumPy and scipy release the GIL for these kernels,
    # so threads execute concurrently without copying full RAW buffers.
    return ThreadPoolExecutor(max_workers=workers,thread_name_prefix='pixel-render')


def run_parallel_rows(length,callback,workers=None,block_rows=128,min_rows=512):
    """Run independent row blocks through the shared renderer worker pool."""
    blocks=[(start,min(start+block_rows,length)) for start in range(0,length,block_rows)]
    workers=lut_worker_count() if workers is None else max(1,int(workers))
    if workers==1 or length<min_rows:
        for start,stop in blocks:callback(start,stop)
        return
    futures=[render_executor(workers).submit(callback,start,stop) for start,stop in blocks]
    for future in futures:future.result()


def _apply_official_rows(source,result,table,start,stop):
    linear=np.einsum('...i,ij->...j',source[start:stop],TO_F_GAMUT)
    video=interpolate(table,flog2_encode(linear))
    display=np.maximum(video,0)**LUT_DISPLAY_GAMMA
    result[start:stop]=np.where(display<=.0031308,display*12.92,
                                1.055*display**(1/2.4)-.055)


def apply_official(linear_srgb,film,workers=None):
    table=load_lut(film)
    result=np.empty_like(linear_srgb,dtype=np.float32)
    # Keep row blocks small to bound temporary memory. Large renders share a
    # process-wide pool; independent exports therefore consume all available
    # cores without each creating an unbounded set of worker threads.
    run_parallel_rows(len(result),lambda start,stop:
        _apply_official_rows(linear_srgb,result,table,start,stop),workers)
    np.clip(result,0,1,out=result)
    return result
