"""Measured X-M5 tone-response approximation in the common display space.

References are paired Classic Negative / DR100 camera exports, fitted on two
scenes and checked on three other scenes. Other films, half steps, and joint
H/S settings are adaptations, not native-camera equivalence. Legacy four-way
RAW recovery is a separate stage and keeps its existing recipe semantics.
"""
from functools import lru_cache
from pathlib import Path
import json
import numpy as np
from scipy.interpolate import PchipInterpolator
from .official_luts import run_parallel_rows

_WEIGHTS = np.array([.2126, .7152, .0722], np.float32)
_AXIS = np.linspace(0, 1, 4097, dtype=np.float32)


def _decode(a):
    return np.where(a <= .04045, a / 12.92,
                    ((np.maximum(a, 0) + .055) / 1.055) ** 2.4)


def _encode(a):
    return np.where(a <= .0031308, a * 12.92,
                    1.055 * np.maximum(a, 0) ** (1 / 2.4) - .055)


@lru_cache(maxsize=1)
def _tables():
    data = json.loads((Path(__file__).with_name('luts') / 'xm5-tone-response.json').read_text())
    levels = np.array(data['levels'], np.float32)
    tables = {}
    for key, values in data['curves'].items():
        values = np.asarray(values, np.float32)
        knots = np.linspace(0, 1, values.shape[1])
        table = PchipInterpolator(knots, values, axis=1)(_AXIS).astype(np.float32)
        zero = int(np.flatnonzero(levels == 0)[0])
        table[zero] = _AXIS
        softer = np.minimum if key == 'highlight' else np.maximum
        harder = np.maximum if key == 'highlight' else np.minimum
        for i in range(zero - 1, -1, -1):table[i] = softer(table[i], table[i + 1])
        for i in range(zero + 1, len(levels)):table[i] = harder(table[i], table[i - 1])
        tables[key] = table
        tables[key].setflags(write=False)
    return levels, tables


def _curve(key, value):
    levels, tables = _tables()
    upper = int(np.clip(np.searchsorted(levels, value, side='right'), 1, len(levels) - 1))
    lower = upper - 1
    weight = (value - levels[lower]) / (levels[upper] - levels[lower])
    return tables[key][lower] * (1 - weight) + tables[key][upper] * weight


@lru_cache(maxsize=169)
def tone_curve(highlight, shadow):
    """Positive H hardens highlights; positive S deepens shadows.

    A monotone composition avoids tone reversals at combined extremes. Each
    half-step is interpolated between measured settings, with exact identity
    at zero. This does not reconstruct detail already clipped by a film LUT.
    """
    curve = _AXIS.copy() if not highlight else _curve('highlight', highlight)
    if shadow:
        curve = np.interp(curve, _AXIS, _curve('shadow', shadow)).astype(np.float32)
    curve.setflags(write=False)
    return curve


def apply_fuji_tone(display, highlight=0, shadow=0):
    if not highlight and not shadow:
        return display
    curve = tone_curve(float(highlight), float(shadow))
    result = np.empty_like(display)

    def process(start, stop):
        linear = _decode(np.clip(display[start:stop], 0, 1))
        y = np.sum(linear * _WEIGHTS, axis=-1)
        target = _decode(np.interp(_encode(y), _AXIS, curve).astype(np.float32))
        linear *= (target / np.maximum(y, 1e-10))[..., None]
        # Compress chroma toward the target grey only if the new luminance
        # leaves the display gamut. Avoid independent RGB clipping/hue shifts.
        peak = np.max(linear, axis=-1)
        chroma_scale = np.minimum(1, (1 - target) / np.maximum(peak - target, 1e-8))
        linear = target[..., None] + (linear - target[..., None]) * chroma_scale[..., None]
        result[start:stop] = np.clip(_encode(linear), 0, 1)

    run_parallel_rows(len(display), process, block_rows=128)
    return result
