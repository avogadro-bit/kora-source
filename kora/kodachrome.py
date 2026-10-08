"""Experimental E-88 film model, evaluated with bounded, reproducible tables.

Input is linear sRGB/D65 AFTER Kora's user exposure. Output is display sRGB.
See docs/KODACHROME64.md for scientific scope, provenance and HDR extension.
"""
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import numpy as np
from scipy.ndimage import map_coordinates
from .official_luts import run_parallel_rows

FILM_ID = 'kodachrome64'
DATA = Path(__file__).with_name('film_data')


@lru_cache(maxsize=1)
def load_model():
    manifest = json.loads((DATA/'kodachrome64_v1.json').read_text())
    asset = DATA/'kodachrome64_v1.npz'
    if hashlib.sha256(asset.read_bytes()).hexdigest() != manifest['sha256']:
        raise ValueError('The Kodachrome model is damaged. Reinstall Kora.')
    with np.load(asset, allow_pickle=False) as archive:
        model = {key: archive[key] for key in archive.files}
    shapes = {'response_axis':(65,), 'responses':(65,65,65,3),
              'logh':(513,), 'amounts':(513,3), 'anchor':(),
              'dye_rgb':(65,65,65,3), 'dye_max':(3,)}
    if set(model) != set(shapes):
        raise ValueError('Unsupported Kodachrome table layout.')
    for key, shape in shapes.items():
        if model[key].shape != shape or not np.isfinite(model[key]).all():
            raise ValueError(f'Invalid Kodachrome table: {key}')
        model[key].setflags(write=False)
    axis = model['response_axis']
    if (axis[0] != 0 or axis[-1] != 1 or not np.all(np.diff(axis)>0)
            or not np.all(np.diff(model['logh'])>0)
            or np.any(model['dye_max']<=0)):
        raise ValueError('Invalid Kodachrome table axes.')
    return model, manifest


def model_info():
    _, meta = load_model()
    return {key:meta[key] for key in ('version','film','label','sha256','base_ev',
            'scene_illuminant','viewing_illuminant','method','limitations')}


def _responses(rgb, model):
    """Four-vertex interpolation, with fractions measured in LINEAR RGB."""
    axis = model['response_axis']
    indices = np.clip(np.searchsorted(axis, rgb, side='right')-1, 0, len(axis)-2)
    fraction = (rgb-axis[indices])/(axis[indices+1]-axis[indices])
    order = np.argsort(-fraction, axis=1, kind='stable')
    fraction = np.take_along_axis(fraction, order, axis=1)
    weights = np.column_stack((1-fraction[:,0], fraction[:,0]-fraction[:,1],
                               fraction[:,1]-fraction[:,2], fraction[:,2]))
    table = model['responses']
    result = np.zeros(rgb.shape, dtype=np.float64)
    rows = np.arange(len(rgb))
    for corner in range(4):
        result += table[indices[:,0],indices[:,1],indices[:,2]]*weights[:,corner,None]
        if corner<3:
            indices[rows,order[:,corner]] += 1
    return result


def apply_kodachrome(linear, exposure=0., *, workers=None):
    """The +0.5 EV conventional anchor is built in; exposure is relative to it.

    Exposure is moved after reflectance reconstruction, matching the study.
    Signed/HDR Kora input uses nonnegative RGB and an intensity factor above
    white; this extension is an approximation, not recovered scene spectra.
    """
    source = np.asarray(linear)
    if source.ndim != 3 or source.shape[-1] != 3:
        raise ValueError('Kodachrome expects an H×W×3 linear sRGB image.')
    if not np.isfinite(exposure) or abs(exposure)>16:
        raise ValueError('Invalid Kodachrome exposure.')
    model, meta = load_model()
    output = np.empty(source.shape, dtype=np.float32)
    gain = 2.**float(exposure)
    ev = (meta['base_ev']+float(exposure))*np.log10(2.)
    def band(start, stop):
        rgb = np.array(source[start:stop], dtype=np.float64).reshape(-1,3)
        if not np.isfinite(rgb).all():
            raise ValueError('Kodachrome input contains non-finite pixels.')
        rgb /= gain
        np.maximum(rgb, 0, out=rgb)
        intensity = np.maximum(rgb.max(axis=1,keepdims=True), 1.)
        rgb /= intensity
        response = _responses(rgb, model)*intensity
        h = float(model['anchor']) + np.log10(np.maximum(response,1e-30)/.18) + ev
        amounts = np.column_stack([np.interp(h[:,c], model['logh'], model['amounts'][:,c])
                                   for c in range(3)])
        coordinates = (amounts/model['dye_max']*64).T
        display = np.column_stack([map_coordinates(model['dye_rgb'][...,c],coordinates,
                                     order=1,mode='nearest',prefilter=False) for c in range(3)])
        np.clip(display,0,1,out=display)
        display = np.where(display<=.0031308, display*12.92,
                           1.055*np.power(display,1/2.4)-.055)
        output[start:stop] = display.reshape(stop-start,source.shape[1],3)
    run_parallel_rows(len(source),band,workers=workers,block_rows=32)
    return output
