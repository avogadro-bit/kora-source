"""Reference-backed approximations, not Fujifilm's complete photo processing.

WB: X-T4 2.12 DAT coefficients; RGB application is an adaptation.
Chrome STRONG: fit to official public pairs, checked on a second X100V scene.
WEAK: half the STRONG response, not measured independently.
See docs/PARAMETER_AUDIT.md and research/reference-effects/chrome-fit.json.
"""
import json
from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import uniform_filter
from .official_luts import run_parallel_rows

WB_TABLE=json.loads((Path(__file__).with_name('luts')/'wb-shifts-xt4.json').read_text())


def wb_shift_gains(red,blue):
    return np.array([WB_TABLE['red_q10'][red+9],1024,
                     WB_TABLE['blue_q10'][blue+9]],np.float32)/1024


def chrome_effect(a,setting,blue_only=False,*,strength_scale=1.):
    if setting=='off':return a
    strength={'weak':.5,'strong':1.}[setting]*strength_scale
    result=np.empty_like(a)
    def process(start,stop):
        source=a[start:stop]
        high=source.max(-1);low=source.min(-1);chroma=high-low
        sat=np.clip(chroma/np.maximum(high,1e-6),0,1)
        y=np.sum(source*np.array([.2126,.7152,.0722],np.float32),axis=-1)
        if blue_only:
            hue=np.clip((source[...,2]-np.maximum(source[...,0],source[...,1]))/np.maximum(chroma,1e-6),0,1)
            mask=sat**1.32407230501026*hue**.3702288353626123
            out=source-strength*.6912800902142242*(mask*y)[...,None]
        else:
            hue=np.clip((np.maximum(source[...,0],source[...,1])-source[...,2])/np.maximum(chroma,1e-6),0,1)
            mask=sat**1.09437228*hue
            density=.15368655*mask
            target=y*(1-density)
            # Refit with bounded chroma: taper extra saturation near the gamut
            # boundary, instead of exaggerating already saturated colors and
            # independently clipping their channels (revision 2).
            gain=1-density+mask*(1-sat)
            gain=np.minimum(gain,target/np.maximum(y-low,1e-6))
            gain=np.minimum(gain,(1-target)/np.maximum(high-y,1e-6))
            strong=target[...,None]+gain[...,None]*(source-y[...,None])
            out=source+strength*(strong-source)
        np.clip(out,0,1,out=result[start:stop])
    run_parallel_rows(len(a),process)
    return result


def dynamic_range_compress(a,level):
    """Shoulder preserving middle gray, mapping 1/2 stops of headroom to white.

    Does not recover sensor highlights absent from the decoded input.
    """
    if level==100:return a
    y=np.sum(a*np.array([.2126,.7152,.0722],np.float32),axis=-1)
    excess=np.maximum(y-.18,0)
    white=level/100
    # f(.18)=.18, f'(.18)=1, f(white)=1. The previous coefficients
    # mapped white to .825 (DR200) / .622 (DR400), needlessly darkening it.
    k=(white-1)/((white-.18)*(1-.18))
    target=np.minimum(y,.18)+excess/(1+k*excess)
    # Signed camera-to-working-space conversion can yield negative out-of-gamut
    # values. Dividing those by a positive epsilon inverted them into enormous
    # positive values, which appeared as isolated white preview pixels after a
    # DR change. DR compression is undefined below zero luminance; leave those
    # samples signed for the film transform to handle instead of inverting them.
    scale=np.ones_like(y)
    np.divide(target,y,out=scale,where=y>1e-8)
    return a*scale[...,None]


def tone_curve(a, highlights=0, shadows=0):
    """Independent, stronger photo tone controls; not a measured Fuji curve.

    Positive shadow values darken; positive highlights brighten. The two
    halves join at display luminance .5 with unit slope. The rational curves
    remain monotonic throughout the recipe's -2..4 range, unlike simply
    multiplying the former additive correction until it folds or clips.
    """
    if highlights == 0 and shadows == 0:
        return a
    a=np.clip(a,0,1)
    y=np.sum(a*np.array([.2126,.7152,.0722],np.float32),axis=-1)
    def half(t,setting):
        return t/(t+(1-t)*np.exp(.8*setting*(1-t)))
    dark=.5*half(np.minimum(2*y,1),shadows)
    light=1-.5*half(np.minimum(2*(1-y),1),highlights)
    target=np.where(y<.5,dark,light)
    # Keep chroma where possible, reduce it only at the display gamut boundary.
    low=a.min(-1);high=a.max(-1)
    gain=np.minimum(1,target/np.maximum(y-low,1e-6))
    gain=np.minimum(gain,(1-target)/np.maximum(high-y,1e-6))
    return np.clip(target[...,None]+gain[...,None]*(a-y[...,None]),0,1)


def _tone_tail(ev, pivot, strength, high):
    """Monotonic log-luminance tail with a fixed point and unit pivot slope."""
    distance=np.maximum(ev-pivot,0) if high else np.maximum(pivot-ev,0)
    # The bounded exponent approaches a constant contrast away from the
    # pivot. It cannot fold the curve over in the supported strength range.
    mapped=distance*np.exp2(strength*distance/(1+distance))
    return np.where(distance>0,pivot+mapped if high else pivot-mapped,ev)


def _smoothstep(value):
    value=np.clip(value,0,1)
    return value*value*(3-2*value)


@lru_cache(maxsize=64)
def _highlight_curve(highlights, whites, legacy=False):
    """Integrate positive contrast on the ORIGINAL exposure axis.

    Both controls select their input zone before compression. Negative edits
    compress a bounded transition, then recover contrast in the bright tail:
    the old permanent 1/16 slope flattened entire skies at combined minima.
    A positive contrast floor prevents reversals even with opposite settings.
    """
    axis=np.linspace(0,32,4097,dtype=np.float64)
    def amount(value):
        t=abs(value)/100
        return .4*t+.6*t*t
    high_zone=_smoothstep(axis/2)
    white_zone=_smoothstep((axis-1.75)/1.)
    if legacy:
        # Freeze the pre-0.2.32 exposure-fit anchor for embedded RAF recipes.
        # This branch is never selected by the user's editing controls.
        slope=np.exp2(((-2 if highlights<0 else .9)*amount(highlights))*high_zone
                      +((-2 if whites<0 else 1.2)*amount(whites))*white_zone)
        mapped=np.concatenate(([0.],np.cumsum((slope[:-1]+slope[1:])*.5*np.diff(axis))))
        axis.setflags(write=False);mapped.setflags(write=False)
        return axis,mapped,float(slope[-1])
    high_window=high_zone*(1-_smoothstep((axis-2)/3))
    white_window=white_zone*(1-_smoothstep((axis-3)/2.5))
    reduction=(.75*amount(min(highlights,0))*high_window
               +amount(min(whites,0))*white_window)
    slope=(.18+.82*np.exp2(-4*reduction))*np.exp2(
        .9*amount(max(highlights,0))*high_zone
        +1.2*amount(max(whites,0))*white_zone)
    mapped=np.concatenate(([0.],np.cumsum((slope[:-1]+slope[1:])*.5*np.diff(axis))))
    axis.setflags(write=False);mapped.setflags(write=False)
    return axis,mapped,float(slope[-1])


def _map_highlights(ev, highlights, whites, legacy=False):
    if highlights==0 and whites==0:return ev
    axis,mapped,last_slope=_highlight_curve(highlights,whites,legacy)
    result=np.interp(ev,axis,mapped).astype(np.float32)
    return np.where(ev<=0,ev,np.where(ev>axis[-1],mapped[-1]+(ev-axis[-1])*last_slope,result))


def linear_tone_curve(a, highlights=0, shadows=0, whites=0, blacks=0, *, detail_scale=0, legacy_highlights=False):
    """Four-way, exposure-domain tonal adjustment before film clipping.

    Values follow common photo-editor directions on a -100..100 scale:
    negative Highlights/Whites recover bright tones, while positive
    Shadows/Blacks open dark tones. Highlights and Whites independently shape
    positive log-luminance contrast on the original exposure axis. Smooth
    overlapping ranges retain HDR gradation and RGB ratios.
    This is an independent Capture One-like model, not Capture One code.
    """
    if highlights == 0 and whites == 0 and shadows == 0 and blacks == 0:
        return a
    result=np.empty_like(a)
    radius=min(64,max(2,round(8*detail_scale))) if detail_scale>0 and min(highlights,whites)<0 else 0
    def process(start,stop):
        lo=max(0,start-2*radius);hi=min(len(a),stop+2*radius)
        source=a[lo:hi]
        y=np.sum(source*np.array([.2126,.7152,.0722],np.float32),axis=-1)
        valid=y>1e-12
        ev=np.log2(np.maximum(y,1e-12)/.18)
        # Shadow controls retain their existing exposure-domain response.
        ev=_tone_tail(ev,-2.5,-1.55*blacks/100,False)
        ev=_tone_tail(ev,0,-1.35*shadows/100,False)
        mapped=_map_highlights(ev,highlights,whites,legacy_highlights)
        if radius:
            # Compress the edge-aware base before the film transform, retaining
            # fine RAW detail. Small epsilon protects high-contrast boundaries;
            # a quarter-stop limit prevents broad local halos at extreme edits.
            base=_guided_base(ev,radius,epsilon=.015)
            detail_target=_map_highlights(base,highlights,whites,legacy_highlights)+(ev-base)
            mapped+=np.clip(detail_target-mapped,-.25,.25)*_smoothstep(ev/1.75)
        ev=mapped
        target=.18*np.exp2(np.clip(ev,-60,60))
        scale=np.ones_like(y)
        np.divide(target,y,out=scale,where=valid)
        result[start:stop]=(source*scale[...,None])[start-lo:stop-lo]
    run_parallel_rows(len(a),process)
    return result


def _resize_plane(a, size):
    """Resize one float32 plane without quantizing it to an image format."""
    return np.asarray(Image.fromarray(a.astype(np.float32), mode='F').resize(
        size, Image.Resampling.BILINEAR), dtype=np.float32)


def _guided_base(a, radius, epsilon=.16):
    """Edge-aware base layer for log-luminance local-contrast separation."""
    size=2*radius+1
    mean=uniform_filter(a,size=size,mode='reflect')
    correlation=uniform_filter(a*a,size=size,mode='reflect')
    variance=np.maximum(correlation-mean*mean,0)
    coefficient=variance/(variance+epsilon)
    offset=mean-coefficient*mean
    return (uniform_filter(coefficient,size=size,mode='reflect')*a
            +uniform_filter(offset,size=size,mode='reflect'))


def selective_tone_detail(original, adjusted, highlights=0, shadows=0, whites=0, blacks=0):
    """Restore shadow texture without locally amplifying bright cloud edges.

    Highlights/Whites are handled by the monotonic RAW tone curve. Adding
    source log-detail after the film shoulder exaggerated small differences
    around clipped clouds into dark lobes and white rims.
    """
    shadow_strength=np.clip(shadows/100,0,1)
    black_strength=np.clip(blacks/100,0,1)
    if max(shadow_strength,black_strength)==0:
        return adjusted

    weights=np.array([.2126,.7152,.0722],np.float32)
    source_y=np.sum(original*weights,-1)
    adjusted_y=np.sum(adjusted*weights,-1)
    h,w=source_y.shape
    edge=min(1200,max(h,w))
    small_size=(max(1,round(w*edge/max(h,w))),max(1,round(h*edge/max(h,w))))
    source_small=_resize_plane(source_y,small_size) if small_size!=(w,h) else source_y
    adjusted_small=_resize_plane(adjusted_y,small_size) if small_size!=(w,h) else adjusted_y

    source_log=np.log2(np.maximum(source_small,2**-16))
    adjusted_log=np.log2(np.maximum(adjusted_small,2**-16))
    radius=max(6,round(min(small_size)/16))
    source_base=_guided_base(source_log,radius)
    adjusted_base=_guided_base(adjusted_log,radius)
    source_detail=source_log-source_base
    # Restore surviving shadow structure removed by the global curve.
    recovered_detail=(source_detail-(adjusted_log-adjusted_base))+.65*source_detail

    base_y=np.exp2(source_base)
    shadow_mask=1-np.clip((base_y-.06)/(.30-.06),0,1)
    shadow_mask=shadow_mask*shadow_mask*(3-2*shadow_mask)
    black_mask=1-np.clip((base_y-.015)/(.085-.015),0,1)
    black_mask=black_mask*black_mask*(3-2*black_mask)
    strength=np.maximum(.75*shadow_strength*shadow_mask,.65*black_strength*black_mask)
    # Bound the shadow-detail adjustment to 0.85 stop.
    gain_small=np.exp2(np.clip(recovered_detail*strength,-.85,.85)).astype(np.float32)
    gain=_resize_plane(gain_small,(w,h)) if small_size!=(w,h) else gain_small
    result=np.empty_like(adjusted)
    def process(start,stop):
        block_gain=np.where((source_y[start:stop]>2**-14)&(adjusted_y[start:stop]>2**-14),
                            gain[start:stop],1)
        # Suppress shadow-detail spill across high-contrast sky/foliage edges
        # after resizing the low-resolution gain plane.
        shadow_gate=1-_smoothstep((source_y[start:stop]-.18)/.17)
        block_gain=1+(block_gain-1)*shadow_gate
        # Scaling preserves hue only while no display channel clips. Let bright
        # detail recover mainly by locally darkening valleys near the white limit.
        block_gain=np.minimum(block_gain,1/np.maximum(adjusted[start:stop].max(-1),1e-8))
        result[start:stop]=adjusted[start:stop]*block_gain[...,None]
    run_parallel_rows(len(adjusted),process)
    return result


def preserve_film_hue(reference, adjusted):
    """Use RAW-adjusted luminance with the reference film's RGB hue direction.

    Near the reference film's white shoulder, use recovered colour instead:
    the baseline rendering has lost chroma there. Elsewhere chroma is scaled
    with luminance and reduced at the gamut boundary, never channel-clipped.
    This is an independent color-stability policy, not Fuji's algorithm.
    """
    weights=np.array([.2126,.7152,.0722],np.float32)
    result=np.empty_like(reference)
    def process(start,stop):
        ref=reference[start:stop];adj=adjusted[start:stop]
        y=np.sum(ref*weights,-1)
        target=np.clip(np.sum(adj*weights,-1),0,1)
        chroma=ref-y[...,None]
        gain=target/np.maximum(y,1e-8)
        gain=np.minimum(gain,target/np.maximum(y-ref.min(-1),1e-8))
        gain=np.minimum(gain,(1-target)/np.maximum(ref.max(-1)-y,1e-8))
        stable=target[...,None]+gain[...,None]*chroma
        recovered_weight=_smoothstep((ref.max(-1)-.85)/.15)[...,None]
        np.clip(stable*(1-recovered_weight)+adj*recovered_weight,0,1,
                out=result[start:stop])
    run_parallel_rows(len(reference),process)
    return result
