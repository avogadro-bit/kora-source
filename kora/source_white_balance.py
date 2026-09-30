"""Separate recorded Fuji WB fine-tuning from the camera's illuminant estimate."""
import re
import numpy as np


def fuji_shift(metadata):
    value=metadata.get('WhiteBalanceFineTune')
    if isinstance(value,str):
        match=re.fullmatch(r'Red\s+([+-]?\d+),?\s+Blue\s+([+-]?\d+)',value.strip(),re.I)
        if not match:return None
        pair=[int(v) for v in match.groups()]
    elif isinstance(value,(list,tuple)) and len(value)==2:
        pair=value
    else:return None
    # Modern Fuji MakerNotes store twenty units per R/B menu step. Do not
    # guess an older camera's units from an arbitrary small nonzero value.
    try:values=np.asarray(pair,dtype=float)/20
    except (TypeError,ValueError):return None
    if not np.isfinite(values).all() or np.any(abs(values)>9) or np.any(values!=np.round(values)):return None
    return tuple(int(v) for v in values)


def _levels(value, channels):
    try:a=np.asarray(value.split() if isinstance(value,str) else value,dtype=float)
    except (TypeError,ValueError):return None
    if a.shape!=(channels,) or not np.isfinite(a).all() or np.any(a<=0) or np.any(a>65535):return None
    # Tags name the channel order: G,R,B or G,R,G,B, never RGB.
    rgbg=a[[1,0,2,0]] if channels==3 else a[[1,0,3,2]]
    if np.max(rgbg)/np.min(rgbg)>16:return None
    return rgbg.tolist()


def source_white_balance(metadata,suffix):
    result={'shift_removed':False,'basis':'camera as shot','user_wb':None}
    if suffix.lower()!='.raf':return result
    shift=fuji_shift(metadata)
    result['recorded_shift']=list(shift) if shift is not None else None
    if shift==(0,0):return {**result,'basis':'camera WB; recorded shift is zero'}
    mode=str(metadata.get('WhiteBalance','')).strip().lower()
    # The ordinary Auto estimate is explicitly recorded separately from the
    # as-shot multipliers. Do not substitute Auto for Kelvin/custom/preset WB,
    # or assume that white/ambience-priority uses the same Auto estimate.
    if shift is not None and mode=='auto':
        for tag,count in [('WB_GRBLevelsAuto',3),('WB_GRGBLevelsAuto',4)]:
            levels=_levels(metadata.get(tag),count)
            if levels is not None:
                return {**result,'shift_removed':True,'basis':tag,'user_wb':levels}
    return {**result,'basis':'camera as shot; unshifted WB unavailable',
            'warning':'Camera WB shift could not be separated for this file.'}
