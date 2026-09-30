"""Sensor-space WB for the X-M5, checked against controlled camera exports.

Other cameras retain the existing relative adaptation until independently
verified. Matrices use row RGB vectors, like the rest of the float renderer.
"""
from functools import lru_cache
from pathlib import Path
import numpy as np
import rawpy
from .raw import exif, require_local
from .source_white_balance import source_white_balance, _levels


# X-M5 1.20 preset coefficients from controlled JPEGs, constant across the
# five source scenes. Normalize green; do not reuse another camera's table.
XM5_PRESETS={
    'daylight':(2168,1208,2188), 'shade':(2396,1208,1884),
    'fluorescent1':(2852,1208,1880), 'fluorescent2':(2404,1208,2312),
    'fluorescent3':(2272,1208,2936), 'tungsten':(1456,1208,3328),
    'underwater':(2212,1208,2140),
}


def camera_to_srgb(rgb_xyz):
    xyz=np.asarray(rgb_xyz,dtype=np.float64)[:3]
    if xyz.shape!=(3,3) or not np.isfinite(xyz).all():
        raise ValueError('Invalid camera matrix')
    srgb_to_xyz=np.array([[.412453,.357580,.180423],
                         [.212671,.715160,.072169],
                         [.019334,.119193,.950227]])
    matrix=np.einsum('ij,jk->ik',xyz,srgb_to_xyz)
    sums=matrix.sum(axis=1)
    if np.any(abs(sums)<1e-8):raise ValueError('Invalid camera matrix')
    matrix/=sums[:,None]
    if np.linalg.cond(matrix)>100:raise ValueError('Unstable camera matrix')
    return np.linalg.inv(matrix).T.astype(np.float32)


@lru_cache(maxsize=128)
def _context(path,mtime,size):
    meta=exif(path)
    if str(meta.get('Model','')).strip().upper()!='X-M5':return {}
    plan=source_white_balance(meta,path.suffix)
    with rawpy.imread(str(path)) as raw:
        matrix=camera_to_srgb(raw.rgb_xyz_matrix)
        base=np.array(plan['user_wb'] if plan['shift_removed'] else raw.camera_whitebalance,dtype=float)[:3]
    result={'camera_to_srgb':matrix,'source_camera':'X-M5'}
    auto=_levels(meta.get('WB_GRBLevelsAuto'),3)
    if np.isfinite(base).all() and np.all(base>0):
        presets=dict(XM5_PRESETS)
        if auto is not None:presets['auto']=auto[:3]
        result['camera_wb_gains']={}
        for mode,values in presets.items():
            values=np.asarray(values,dtype=float)
            gains=(values/values[1])/(base/base[1])
            result['camera_wb_gains'][mode]=gains.astype(np.float32)
    return result


def source_render_context(path):
    path=Path(path)
    if path.suffix.lower()!='.raf':return {}
    require_local(path);stat=path.stat()
    return dict(_context(path,stat.st_mtime_ns,stat.st_size))


def apply_sensor_gains(pixels,gains,matrix):
    """Apply a diagonal sensor WB in working RGB without clipping intermediates."""
    if np.array_equal(gains,np.ones(3)):return pixels
    matrix=np.asarray(matrix,dtype=np.float32)
    transform=np.einsum('ij,jk->ik',np.linalg.inv(matrix)*gains[None,:],matrix)
    return np.einsum('...i,ij->...j',pixels,transform).astype(np.float32)
