"""Estimate clipped camera channels from surviving channels and nearby ratios.

This is a local colour estimate, not measured colour in saturated sensels.
Work before the camera matrix; two Bayer green sites are one colour channel.
"""
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter


def _resize(a, size):
    if a.shape[::-1] == tuple(size):
        return a
    return np.asarray(Image.fromarray(a).resize(size, Image.Resampling.BILINEAR))


def clipped_neutral_mask(raw, white_balance=None):
    """Fade unreliable chroma in sensor-clipped, near-neutral Bayer highlights.

    Balance the surviving sensels before deciding how close to white they
    are: a neutral surface does not have equal unbalanced sensor values.
    Unsupported layouts retain their decoder's existing behaviour.
    """
    sensor=raw.raw_image_visible
    pattern=raw.raw_pattern
    if (sensor.ndim!=2 or pattern is None or pattern.shape!=(2,2)
            or raw.color_desc!=b'RGBG'
            or not set(pattern.ravel()).issubset({0,1,2,3})
            or not {0,1,2}.issubset(set(pattern.ravel()))):
        return None
    wb=np.array(raw.camera_whitebalance if white_balance is None else white_balance,dtype=np.float32)
    if wb.shape!=(4,) or not np.isfinite(wb).all() or np.any(wb[:3]<=0):return None
    if wb[3]<=0:wb[3]=wb[1]
    wb/=wb.min()
    h,w=sensor.shape;h-=h%2;w-=w%2
    lowest=np.full((h//2,w//2),np.inf,np.float32)
    clipped=np.zeros_like(lowest)
    for yy in (0,1):
        for xx in (0,1):
            index=int(pattern[yy,xx]);black=raw.black_level_per_channel[index]
            if raw.white_level<=black:return None
            level=(sensor[yy:h:2,xx:w:2].astype(np.float32)-black)/(raw.white_level-black)
            np.minimum(lowest,level*wb[index],out=lowest)
            weight=np.clip((level-.94)/.06,0,1)
            np.maximum(clipped,weight*weight*(3-2*weight),out=clipped)
    neutral=np.clip((lowest-.6)/.4,0,1)
    neutral=neutral*neutral*(3-2*neutral)*clipped
    if raw.sizes.flip in (3,5,6):neutral=np.rot90(neutral,{3:2,5:1,6:3}[raw.sizes.flip])
    return neutral


def neutralize_clipped_rgb(rgb, mask, *, preview):
    """Suppress uncertain colour without clipping luminance or RAW headroom."""
    if mask is None or not np.any(mask):return rgb
    mask=gaussian_filter(_resize(mask,(rgb.shape[1],rgb.shape[0])),.6 if preview else 1.2)
    result=rgb.astype(np.float32,copy=True)
    # Bound temporary memory on 100+ MP files.
    for start in range(0,len(result),128):
        row=result[start:start+128];weight=mask[start:start+128,:,None]
        y=np.sum(row*np.array([.2126,.7152,.0722],np.float32),-1,keepdims=True)
        row+=weight*(y-row)
    return result


def bayer_clipping(raw, *, with_neutralization=False):
    sensor=raw.raw_image_visible
    pattern=raw.raw_pattern
    if sensor.ndim!=2 or pattern is None or pattern.shape!=(2,2):
        raise ValueError('Unsupported floating-point DNG sensor layout.')
    if not set(np.asarray(pattern).ravel()).issubset({0,1,2,3}) or not {0,1,2}.issubset(set(np.asarray(pattern).ravel())):
        raise ValueError('Unsupported floating-point DNG colour pattern.')
    h,w=sensor.shape;h-=h%2;w-=w%2
    masks=np.zeros((h//2,w//2,3),np.float32)
    counts=np.zeros(3,np.int32)
    lowest=np.ones((h//2,w//2),np.float32) if with_neutralization else None
    for yy in (0,1):
        for xx in (0,1):
            index=int(pattern[yy,xx]);channel=1 if index==3 else index
            black=raw.black_level_per_channel[index]
            level=(sensor[yy:h:2,xx:w:2].astype(np.float32)-black)/(raw.white_level-black)
            if lowest is not None:np.minimum(lowest,level,out=lowest)
            weight=np.clip((level-.94)/.06,0,1)
            masks[...,channel]+=weight*weight*(3-2*weight)
            counts[channel]+=1
    masks/=counts
    if lowest is not None:
        # Once a channel is lost, fade uncertain reconstructed chroma as the
        # LAST surviving sensel approaches saturation. Waiting until 94% on
        # every channel produced abrupt coloured rims around white plateaus.
        neutral=np.clip((lowest-.6)/.4,0,1)
        neutral=neutral*neutral*(3-2*neutral)*np.max(masks,axis=-1)
    flip=raw.sizes.flip
    if flip in (3,5,6):
        turns={3:2,5:1,6:3}[flip]
        masks=np.rot90(masks,turns)
        if lowest is not None:neutral=np.rot90(neutral,turns)
    if lowest is not None:return masks,neutral
    return masks


def _smooth_highlight_ratio(small, mask, channel, anchor, limit):
    # Dark foreground objects are poor colour donors for a clipped sky.
    # Every donor colour must survive. Separate two-channel donor sets can
    # disagree about the third channel and paint a green/cyan band into a sky
    # where two channels are lost. Never propagate another clipped colour.
    valid=((np.max(mask,axis=-1)<.01)
           &(small[...,channel]>.6*limit)&(small[...,anchor]>.03*limit))
    if not np.any(valid):return None
    ratio=np.clip(small[...,channel]/np.maximum(small[...,anchor],1e-6),.05,20)
    samples=ratio[valid]
    lo,hi=np.quantile(samples,[.02,.98])
    ratio=np.clip(ratio,lo,hi)
    known=valid.astype(np.float32)
    value=np.full_like(ratio,np.median(samples))
    # Normalized convolution has no nearest-donor region boundaries. Broad
    # estimates blend into local estimates only where enough donors exist.
    for radius in (128,32,8,2):
        mass=gaussian_filter(known,radius)
        mean=gaussian_filter(ratio*known,radius)/np.maximum(mass,1e-6)
        confidence=np.clip(mass/.08,0,1)
        confidence*=confidence*(3-2*confidence)
        value=value*(1-confidence)+mean*confidence
    return value


def recover_camera_highlights(camera, clipping):
    """Estimate missing colour smoothly while retaining surviving texture.

    Fully saturated pixels have no recoverable detail. Keep a bounded colour
    estimate there so losing the last anchor does not drop their luminance;
    the caller neutralizes them after the camera matrix. This is an estimate,
    not a reconstruction of the original scene colour.
    """
    if not np.any(clipping):return camera
    h,w=camera.shape[:2]
    scale=min(1,600/max(h,w))
    size=(max(1,round(w*scale)),max(1,round(h*scale)))
    small=np.stack([_resize(camera[...,c],size) for c in range(3)],-1)
    mask=np.stack([_resize(clipping[...,c],size) for c in range(3)],-1)
    result=camera.copy()
    for c in range(3):
        lost=mask[...,c]>.01
        if not np.any(lost):continue
        limit=float(np.median(small[...,c][lost]))
        estimates=[]
        for anchor in range(3):
            if anchor==c:continue
            ratio=_smooth_highlight_ratio(small,mask,c,anchor,limit)
            if ratio is not None:estimates.append((anchor,ratio))
        if not estimates:continue
        target_mask=_resize(clipping[...,c],(w,h))
        numerator=np.zeros((h,w),np.float32)
        denominator=np.zeros_like(numerator)
        fallback=np.zeros_like(numerator)
        for anchor,ratio in estimates:
            ratio=_resize(ratio,(w,h))
            reliability=1-_resize(clipping[...,anchor],(w,h))
            for start in range(0,h,128):
                sl=slice(start,start+128)
                weight=reliability[sl]**2
                estimate=camera[sl,:,anchor]*ratio[sl]
                numerator[sl]+=estimate*weight
                denominator[sl]+=weight
                fallback[sl]=np.maximum(fallback[sl],estimate)
        for start in range(0,h,128):
            sl=slice(start,start+128)
            # A continuous prior survives when every anchor becomes clipped.
            estimate=(numerator[sl]+.01*fallback[sl])/(denominator[sl]+.01)
            original=camera[sl,:,c]
            correction=np.maximum(np.minimum(estimate,original*4)-original,0)
            result[sl,:,c]+=target_mask[sl]*correction
    return result
