"""Deterministic Fuji-inspired grain on a fixed photographic coordinate plane.

An independent texture model fitted to X-M5 paired grain exports.
It approximates measured amplitude/correlation; it is not the camera algorithm.
Size controls correlation length; strength controls luminance roughness.
Reduced views integrate the texture instead of normalizing noise back to full
strength. No image detail is blurred to make the grain.
"""
from functools import lru_cache
import math
import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates
from .official_luts import run_parallel_rows


def _coordinate_noise(shape, origin=(0,0), seed=71821):
    """Normal variates on an infinite integer lattice (also negative indices)."""
    x=np.arange(origin[1],origin[1]+shape[1],dtype=np.int64).astype(np.uint64)[None,:]
    y=np.arange(origin[0],origin[0]+shape[0],dtype=np.int64).astype(np.uint64)[:,None]
    def uniform(salt):
        value=x*np.uint64(0x9E3779B185EBCA87)^y*np.uint64(0xC2B2AE3D27D4EB4F)^np.uint64(salt)
        value^=value>>np.uint64(30);value*=np.uint64(0xBF58476D1CE4E5B9)
        value^=value>>np.uint64(27);value*=np.uint64(0x94D049BB133111EB)
        value^=value>>np.uint64(31)
        return ((value>>np.uint64(11)).astype(np.float64)+.5)*(1/2**53)
    return (np.sqrt(-2*np.log(uniform(seed)))*np.cos(2*np.pi*uniform(seed+27352))).astype(np.float32)


def _radii(size):
    return (.548694,.931861) if size=='small' else (.858326,2.574674)


def _coarse_mix(size):
    return .95 if size=='small' else .409928


@lru_cache(maxsize=2)
def _grain_deviation(size):
    # One fixed calibration, independent of output scale or tile contents.
    noise=_coordinate_noise((384,384),(-192,-192))
    fine,coarse=_radii(size)
    field=gaussian_filter(noise,fine)-_coarse_mix(size)*gaussian_filter(noise,coarse)
    return float(field[16:-16,16:-16].std())


def _grain_rows(shape,size,scale,origin,start,stop):
    # Pixel centers in a reference frame whose long edge is 6000 pixels.
    # Each band includes actual neighbouring samples on all four sides.
    fine,coarse=_radii(size)
    samples=max(1,math.ceil(1/scale)) if scale>=.125 else 1
    footprint=max(0.,(1/scale**2-1)/12) if scale<.125 else 0.
    fine=math.sqrt(fine*fine+footprint)
    coarse=math.sqrt(coarse*coarse+footprint)
    halo=math.ceil(4*coarse)+2
    xs=((np.arange(shape[1]*samples,dtype=np.float64)+.5)/samples+origin[1])/scale-.5
    ys=((np.arange(start*samples,stop*samples,dtype=np.float64)+.5)/samples+origin[0])/scale-.5
    left=math.floor(xs[0])-halo;top=math.floor(ys[0])-halo
    right=math.ceil(xs[-1])+halo+1;bottom=math.ceil(ys[-1])+halo+1
    noise=_coordinate_noise((bottom-top,right-left),(top,left))
    field=(gaussian_filter(noise,fine)-_coarse_mix(size)*gaussian_filter(noise,coarse))/_grain_deviation(size)
    coords=np.broadcast_arrays((ys-top)[:,None],(xs-left)[None,:])
    sampled=map_coordinates(field,coords,order=1,prefilter=False,mode='nearest')
    if samples==1:return sampled
    return sampled.reshape(stop-start,samples,shape[1],samples).mean((1,3))


def film_grain(shape,size,scale=1,origin=(0,0)):
    """Render the same grain plane at any view scale, with bounded row memory."""
    if size not in ('small','large') or not math.isfinite(scale) or scale<=0:
        raise ValueError('Invalid grain size or scale')
    result=np.empty(shape,np.float32)
    # Small previews cover more reference rows per output row.
    rows=max(8,min(128,round(128*scale)))
    def process(start,stop):
        result[start:stop]=_grain_rows(shape,size,scale,origin,start,stop)
    run_parallel_rows(shape[0],process,block_rows=rows)
    return result


def apply_film_grain(a,strength,size,scale=1,origin=(0,0)):
    """Add fine luminance roughness, preserving black/white and RGB hue direction."""
    if strength=='off':return
    amount=({'weak':.0441285,'strong':.089436} if size=='small'
            else {'weak':.0157737,'strong':.0330474})[strength]
    if size not in ('small','large') or not math.isfinite(scale) or scale<=0:
        raise ValueError('Invalid grain size or scale')
    weights=np.array([.2126,.7152,.0722],np.float32)
    shape=a.shape[:2]
    rows=max(8,min(128,round(128*scale)))
    def process(start,stop):
        block=a[start:stop]
        y=np.clip(np.sum(block*weights,-1),0,1)
        field=_grain_rows(shape,size,scale,origin,start,stop)
        # X-M5 paired exports: nearly achromatic, approximately constant
        # amplitude through midtones, SMALL stronger per pixel than LARGE.
        # Retain endpoint protection rather than reproducing camera clipping.
        shadow=np.clip(y/.08,0,1);light=np.clip((1-y)/.08,0,1)
        visibility=(shadow*shadow*(3-2*shadow))*(light*light*(3-2*light))
        target=np.clip(y+amount*visibility*field,0,1)
        gain=np.minimum(1,np.minimum(target/np.maximum(y-block.min(-1),1e-8),
                        (1-target)/np.maximum(block.max(-1)-y,1e-8)))
        block[:]=target[...,None]+gain[...,None]*(block-y[...,None])
        np.clip(block,0,1,out=block)
    run_parallel_rows(shape[0],process,block_rows=rows)
