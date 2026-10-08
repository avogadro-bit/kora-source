"""Independent photographic renderer. No Fuji firmware or calibrated Fuji model."""
from io import BytesIO
from functools import lru_cache
from pathlib import Path
from typing import Literal
import json
import threading
import numpy as np
from PIL import Image, ImageCms
from pydantic import Field
import rawpy
from scipy.ndimage import gaussian_filter
import tifffile
from .input_profiles import RAW_EXTENSIONS, validate_linear_input, normalization_details, apply_input_color
from .recipe import Recipe, FujiFilm
from .grain import apply_film_grain
from .fuji_tone import apply_fuji_tone
from .highlight_recovery import (bayer_clipping, recover_camera_highlights,
                                 clipped_neutral_mask, neutralize_clipped_rgb)
from .raw import require_local, exif
from .source_exposure import source_exposure, estimate_reference_ev
from .source_white_balance import source_white_balance, fuji_shift
from .camera_white_balance import apply_sensor_gains
from .official_luts import FILMS as OFFICIAL_FILMS, apply_official, run_parallel_rows, MissingLUTError
from .recipe_effects import wb_shift_gains, chrome_effect, dynamic_range_compress, linear_tone_curve, selective_tone_detail, preserve_film_hue


class StudioRecipe(Recipe):
    film: FujiFilm | Literal['kodachrome64'] = 'provia'
    highlight_tone: float = Field(default=0, ge=-2, le=4, multiple_of=.5)
    shadow_tone: float = Field(default=0, ge=-2, le=4, multiple_of=.5)
    highlights: float = Field(default=0, ge=-100, le=100)
    whites: float = Field(default=0, ge=-100, le=100)
    target_model: Literal['X-T4', 'X100VI'] = 'X100VI'
    firmware_version: str = ''
    wb: Literal['camera','auto','auto_white','auto_ambience','daylight','shade','tungsten','fluorescent1','fluorescent2','fluorescent3','underwater','kelvin'] = 'camera'
    dr_priority: Literal['off','weak','strong','auto'] = 'off'
    mono_warm: int = Field(default=0, ge=-18, le=18)
    mono_green: int = Field(default=0, ge=-18, le=18)
    smooth_skin: Literal['off','weak','strong'] = 'off'
    file_type: Literal['jpeg','tiff8','tiff16'] = 'jpeg'
    image_size: Literal['L','M','S'] = 'L'
    aspect: Literal['original','3:2','16:9','1:1','4:3'] = 'original'
    image_quality: Literal['fine','normal'] = 'fine'
    color_space: Literal['srgb','adobe_rgb'] = 'srgb'
    digital_crop: Literal[1,1.4,2] = 1
    lens_optimizer: Literal['off'] = 'off'
    lens_distortion: Literal['off','auto'] = 'off'
    lens_vignetting: Literal['off','auto'] = 'off'
    hdr: Literal['off'] = 'off'


def studio_status():
    from . import __version__
    from .official_luts import missing_luts
    return {'app_version':__version__,'engine':'official-lut-photo-adapter-v1','available':True,'exact_fuji_render':False,
            'missing_luts':missing_luts(),
            'calibrated_against_fuji':False,'default_film':'provia',
            'official_lut_films':list(OFFICIAL_FILMS),
            'special_films':{'kodachrome64':{'experimental':True,'model_version':1,'base_ev':.5}},
            'lut_source':'FUJIFILM GFX ETERNA 55 v1.10',
            'photo_adapter_calibrated':False,'recipe_response_revision':24,
            'tone_reference':{'camera':'X-M5','firmware':'1.20','film':'classic_negative',
                'dynamic_range':100,'fit_scenes':2,'validation_scenes':3,
                'controls':['highlight_tone','shadow_tone'],'range':[-2,4],'step':.5,
                'scope':'all-supported-raw','intermediate_levels':'interpolated',
                'joint_response_validated':False,'other_films_response_validated':False,
                'exact_fuji_render':False},
            'lut_display_gamma':2.2,'raw_extensions':sorted(RAW_EXTENSIONS),
            'input_working_space':'linear sRGB / D65 / float32',
            'wb_shift_source':'X-T4 2.12 coefficients; X-M5 sensor-space application checked',
            'reference_film_scope':'all-supported-raw',
            'reference_film_camera':'X-M5',
            'reference_film_camera_equivalence':False,
            'xm5_reference_validation':{'firmware':'1.20','scenes':5,'complete_camera_equivalence':False,
                'parameters':['Auto WB','WB presets','R/B shift','grain','Color Chrome'],
                'films':['pro_neg_hi','nostalgic_negative','classic_negative']},
            'grain_reference':'X-M5 paired exports; statistical approximation',
            'chrome_reference':'public Fuji pairs; X-M5 strength checked on five scenes'}


def _resize_float_to(a,size,resample=Image.Resampling.LANCZOS):
    if (a.shape[1],a.shape[0])==tuple(size):return a
    return np.stack([np.asarray(Image.fromarray(a[:,:,c]).resize(size,resample))
                     for c in range(3)],axis=-1)


def resize_float(a, edge):
    h,w=a.shape[:2]
    if max(h,w)<=edge:return a
    size=(max(1,round(w*edge/max(h,w))),max(1,round(h*edge/max(h,w))))
    return _resize_float_to(a,size)


def _decode_sensor(path, preview=True, floating_camera_rgb=False, *, user_wb=None):
    require_local(path)
    with rawpy.imread(str(path)) as raw:
        black=min(raw.black_level_per_channel)
        highlight_mask=None
        if floating_camera_rgb:
            clipping,highlight_mask=bayer_clipping(raw,with_neutralization=True)
        else:
            highlight_mask=clipped_neutral_mask(raw,user_wb)
        # Reserve 3 stops inside LibRaw's integer processing BEFORE WB/RGB
        # conversion. Restore the scale in float, with no clip to display white.
        white=black+8*(raw.white_level-black)
        wb_options={'use_camera_wb':True} if user_wb is None else {'use_camera_wb':False,'user_wb':user_wb}
        a=raw.postprocess(**wb_options,use_auto_wb=False,no_auto_bright=True,
            adjust_maximum_thr=0,user_sat=int(white),output_bps=16,gamma=(1,1),
            output_color=rawpy.ColorSpace.raw if floating_camera_rgb else rawpy.ColorSpace.sRGB,half_size=preview)
        if floating_camera_rgb:
            # LibRaw has already decoded the sensor, applied its black/white
            # levels and camera WB. Apply its DNG-derived camera matrix in
            # float instead of its uint16 RGB conversion, retaining signed
            # out-of-sRGB colours and the reserved three stops of headroom.
            matrix=np.asarray(raw.color_matrix,dtype=np.float32)
            if (a.shape[-1]!=3 or matrix.shape!=(3,4) or not np.isfinite(matrix).all()
                    or np.max(np.abs(matrix[:,:3]))<.01 or np.any(matrix[:,3]!=0)):
                raise ValueError('Unsupported DNG color matrix; conversion stopped.')
            camera=recover_camera_highlights(a.astype(np.float32),clipping)
            mask=np.asarray(Image.fromarray(highlight_mask).resize((a.shape[1],a.shape[0]),Image.Resampling.BILINEAR))
            # Smoothly reduce uncertain colour as the last channel saturates;
            # retain luminance and RAW headroom, never manufacture texture.
            mask=blur(mask,.6 if preview else 1.2)[:,:,None]
            a=np.empty_like(camera)
            def convert(start,stop):
                rgb=np.einsum('...j,ij->...i',camera[start:stop],matrix[:,:3])
                weight=mask[start:stop]
                y=np.sum(rgb*np.array([.2126,.7152,.0722],np.float32),-1,keepdims=True)
                a[start:stop]=rgb*(1-weight)+y*weight
            # Independent row bands keep the same arithmetic while avoiding
            # several 60–100 MP temporaries and using the shared worker pool.
            run_parallel_rows(len(a),convert)
        else:
            a=neutralize_clipped_rgb(a,highlight_mask,preview=preview)
        reference=None
        if preview:
            try:
                thumb=raw.extract_thumb()
                im=Image.open(BytesIO(thumb.data)) if thumb.format==rawpy.ThumbFormat.JPEG else Image.fromarray(thumb.data)
                im=im.convert('RGB');im.thumbnail((256,256),Image.Resampling.LANCZOS)
                reference=np.asarray(im,dtype=np.float32)/255
            except (rawpy.LibRawNoThumbnailError,rawpy.LibRawUnsupportedThumbnailError,OSError,ValueError):
                pass
    a=np.asarray(a,dtype=np.float32)
    a*=8/65535
    # A responsive whole-image proxy. Source pixels are requested separately
    # as viewport tiles at 100%+, so edits never rebuild a giant browser JPEG.
    a=resize_float(a,1800) if preview else a
    return (a if floating_camera_rgb else np.maximum(a,0)),reference


@lru_cache(maxsize=16)
def _source_lock(path):
    return threading.Lock()


def _preview_source(path,mtime,size):
    # Metadata inspection and early full decoding can ask for the exposure
    # anchor together. Only one computes it; both use identical cached data.
    with _source_lock(path):
        return _cached_preview_source(path,mtime,size)


@lru_cache(maxsize=3)
def _cached_preview_source(path,mtime,size):
    metadata=exif(path)
    info=source_exposure(metadata,path.suffix)
    wb=source_white_balance(metadata,path.suffix)
    if info.get('floating_camera_rgb'):
        linear,reference=_decode_sensor(path,True,floating_camera_rgb=True)
    elif wb['shift_removed']:
        linear,reference=_decode_sensor(path,True,user_wb=wb['user_wb'])
    else:
        linear,reference=_decode_sensor(path,True)
    linear*=info['gain']
    match={'reference_ev':0.,'reference_matched':False,'reason':'No readable embedded preview'}
    if reference is not None:
        # Fit exposure against a separately decoded AS-SHOT reference. The
        # shifted embedded JPEG must not change the neutral base's WB or make
        # the exposure fit compensate for the removed colour cast.
        anchor=linear
        if wb['shift_removed']:
            anchor,_=_decode_sensor(path,True)
            anchor*=info['gain']
        settings={'film':'provia'}
        # Preserve the source-exposure anchor used by existing recipes. The
        # new camera-style tone controls must not silently re-expose old RAWs.
        if path.suffix.lower()=='.raf':settings.update(shooting_settings(metadata, legacy_tone=True))
        ref_recipe=StudioRecipe(**settings)
        try:
            match=estimate_reference_ev(resize_float(anchor,256),reference,
                                        lambda a:render(a,ref_recipe,context={'source_exposure_anchor':True}))
        except MissingLUTError:
            # Built-in films can use the metadata exposure anchor without
            # the optional Fuji pack. Other LUT errors still surface.
            match['reason']='Embedded exposure match unavailable without the source Fuji LUT'
    info={**info,**match,'metadata_ev':info.get('baseline_ev',info['ev'])}
    info['ev']+=match['reference_ev'];info['gain']=2**info['ev']
    linear*=2**match['reference_ev']
    # Keep the pair-derived colour refinement separate from preview exposure
    # estimation, and apply it identically to preview and full-size decodes.
    linear=apply_input_color(linear,info.get('input_profile'))
    linear=validate_linear_input(linear)
    info['white_balance']=wb
    info['normalization']=normalization_details(metadata,path.suffix,info)
    linear.setflags(write=False)
    return linear,info


_preview_source.cache_clear=_cached_preview_source.cache_clear


def source_details(path):
    path=Path(path);require_local(path);st=path.stat()
    return dict(_preview_source(path,st.st_mtime_ns,st.st_size)[1])


def decode(path, preview=True):
    path=Path(path);require_local(path);st=path.stat()
    if preview:return _preview_source(path,st.st_mtime_ns,st.st_size)[0].copy()
    # Full sensor decoding does not depend on the exposure fit. Start it
    # while inspection prepares that fit, instead of waiting for it first.
    metadata=exif(path)
    info=source_exposure(metadata,path.suffix)
    wb=source_white_balance(metadata,path.suffix)
    if info.get('floating_camera_rgb'):
        a,_=_decode_sensor(path,False,floating_camera_rgb=True)
    elif wb['shift_removed']:
        a,_=_decode_sensor(path,False,user_wb=wb['user_wb'])
    else:
        a,_=_decode_sensor(path,False)
    _,info=_preview_source(path,st.st_mtime_ns,st.st_size)
    return validate_linear_input(apply_input_color(a*info['gain'],info.get('input_profile')))


def srgb_encode(a):
    a=np.maximum(a,0)
    return np.where(a<=.0031308,a*12.92,1.055*a**(1/2.4)-.055)


def srgb_decode(a):
    return np.where(a<=.04045,a/12.92,((a+.055)/1.055)**2.4)


def blur(a, radius):
    sigma=(radius,radius,0) if a.ndim==3 else (radius,radius)
    if len(a)<512 or radius>16:return gaussian_filter(a,sigma=sigma,mode='reflect')
    result=np.empty_like(a);halo=max(1,int(4*radius+.5))
    def process(start,stop):
        top=max(0,start-halo);bottom=min(len(a),stop+halo)
        filtered=gaussian_filter(a[top:bottom],sigma=sigma,mode='reflect')
        result[start:stop]=filtered[start-top:stop-top]
    run_parallel_rows(len(a),process,block_rows=256)
    return result


def large_radius_blur(a,radius):
    """Approximate a broad blur on a reduced float image, then restore size.

    Clarity uses a radius proportional to source resolution (about 63 pixels
    on a 60 MP file). A direct separable Gaussian spends tens of seconds on
    that kernel. Reducing until the working radius is at most 12 pixels keeps
    the same broad-frequency separation with bounded work and memory.
    """
    factor=max(1.,float(radius)/12)
    if factor<=1:return blur(a,radius)
    h,w=a.shape[:2]
    size=(max(1,round(w/factor)),max(1,round(h/factor)))
    small=_resize_float_to(a,size,Image.Resampling.BILINEAR)
    small=blur(small,radius/factor)
    return _resize_float_to(small,(w,h),Image.Resampling.BILINEAR)


def _apply_legacy_film(a,film):
    """Apply one of the explicitly artistic, non-official display looks."""
    a=np.clip(srgb_encode(a),0,1)
    contrast,sat={'pro_neg_hi':(1.1,.94),'nostalgic_negative':(1.06,.93)}.get(film,(1.,1.))
    if film=='nostalgic_negative':
        y=np.sum(a*np.array([.2126,.7152,.0722],np.float32),axis=2)
        a+=y[:,:,None]**2*np.array([.035,.012,-.025],np.float32)
    a=a+(contrast-1)*4*(a-.5)*a*(1-a)
    return a,sat


def render(linear, r, neutral=False, *, output_transform=True, context=None, origin=(0,0)):
    """float32 display sRGB; recipe effects are deterministic artistic approximations."""
    a=linear.astype(np.float32,copy=True)
    context=context or {}
    statistics=np.asarray(context.get('sample',a[::8,::8]),dtype=np.float32)
    if not neutral:
        native_gains=context.get('camera_wb_gains',{}).get(r.wb)
        sensor_matrix=context.get('camera_to_srgb')
        if native_gains is not None:
            gains=np.asarray(native_gains,dtype=np.float32)
        elif r.wb.startswith('auto'):
            means=np.mean(statistics,axis=(0,1))+1e-5
            strength={'auto':.65,'auto_white':1.,'auto_ambience':.3}[r.wb]
            gains=np.clip((means.mean()/means)**strength,.5,2)
        else:
            # Relative temperature adaptation of camera-balanced RGB; not sensor-space WB.
            temp={'daylight':5500,'shade':7500,'tungsten':3200,'fluorescent1':6500,'fluorescent2':5000,'fluorescent3':4000,'underwater':8500}.get(r.wb,r.kelvin if r.wb=='kelvin' else 5500)
            t=np.log(temp/5500)
            gains=np.array([np.exp(.5*t),1,np.exp(-.65*t)],np.float32)
        shifts=wb_shift_gains(r.wb_red,r.wb_blue)
        if sensor_matrix is not None:
            # Relative artistic modes stay in working RGB; a recorded Auto
            # estimate and R/B fine tuning belong to camera RGB instead.
            if native_gains is None:
                a*=gains;statistics=statistics*gains
                gains=np.ones(3,dtype=np.float32)
            a=apply_sensor_gains(a,gains*shifts,sensor_matrix)*2**r.exposure
            adjusted_statistics=apply_sensor_gains(statistics,gains*shifts,sensor_matrix)*2**r.exposure
        else:
            gains=gains*shifts*2**r.exposure
            a*=gains
            adjusted_statistics=statistics*gains
        dr=r.dynamic_range
        if r.dr_priority!='off':
            # D-range priority takes over both DR and manual tone controls.
            dr={'weak':200,'strong':400,'auto':400 if np.percentile(adjusted_statistics,99)>.8 else 200}[r.dr_priority]
        if r.dr_priority=='off':
            highlights,whites,shadows,blacks=r.highlights,r.whites,r.shadows,r.blacks
        else:
            # Priority owns the complete four-way tone group.
            highlights,whites,shadows,blacks=((-35,-12,20,5) if dr==200
                                               else (-55,-28,38,12))
        color_input=a
        stabilize_color=any((highlights,whites,shadows,blacks)) or dr!=100
        a=linear_tone_curve(a,highlights=highlights,whites=whites,
                            shadows=shadows,blacks=blacks,
                            detail_scale=max(context.get('full_shape',a.shape)[:2])/1800,
                            legacy_highlights=context.get('source_exposure_anchor',False))
        a=dynamic_range_compress(a,dr)
    if neutral:
        a=np.clip(srgb_encode(a),0,1)
        return transform_output(a,r) if output_transform else a
    official=r.film in OFFICIAL_FILMS
    # All RAW decoders supply the same linear sRGB/D65 working space.
    # Film adaptations use that space; camera-specific WB stays upstream.
    reference_film=r.film in ('pro_neg_hi','nostalgic_negative','classic_negative')
    film_reference=None
    if r.film=='kodachrome64':
        from .kodachrome import apply_kodachrome
        a=apply_kodachrome(a,r.exposure)
        if stabilize_color:
            film_reference=apply_kodachrome(color_input,r.exposure)
            a=preserve_film_hue(film_reference,a)
        sat=1.
    elif reference_film:
        from .xm5_film import apply_reference_film
        a=apply_reference_film(a,r.film)
        if stabilize_color:
            film_reference=apply_reference_film(color_input,r.film)
            a=preserve_film_hue(film_reference,a)
        sat=1.
    elif official:
        if r.film=='acros' and r.mono_filter!='none':
            # Artistic prefilter; the official pack only supplies plain ACROS.
            gains={'red':[1.5,.8,.4],'yellow':[1.2,1.1,.5],
                   'green':[.7,1.25,.7]}[r.mono_filter]
            a=a*np.array(gains,np.float32)
            color_input=color_input*np.array(gains,np.float32)
        a=apply_official(a,r.film)
        if stabilize_color:
            # Tone changes can move hue inside a 3D film LUT. Keep the film's
            # hue where reliable, using recovered colour near the film shoulder.
            film_reference=apply_official(color_input,r.film)
            a=preserve_film_hue(film_reference,a)
        sat=1.
    else:
        # Legacy artistic looks are explicitly identified in the GUI.
        a,sat=_apply_legacy_film(a,r.film)
    if shadows>0 or blacks>0:
        # Restore shadow texture; highlight recovery remains a smooth point
        # transform to avoid bright/dark rims around cloud boundaries.
        a=selective_tone_detail(color_input,a,highlights=highlights,whites=whites,
                                shadows=shadows,blacks=blacks)
    if r.dr_priority=='off':
        a=apply_fuji_tone(a,r.highlight_tone,r.shadow_tone)
    saturation=sat*(1+r.color*.085)
    if saturation!=1:
        y=np.sum(a*np.array([.2126,.7152,.0722],np.float32),axis=2)
        a=y[:,:,None]+(a-y[:,:,None])*saturation
    if r.color_chrome!='off':
        # Apply the reference-derived strength in the common display space.
        # This is an artistic adaptation, not a calibration of other cameras.
        a=chrome_effect(a,r.color_chrome,strength_scale=.437)
    if r.fx_blue!='off':a=chrome_effect(a,r.fx_blue,blue_only=True)
    if r.film in ['acros','monochrome','sepia']:
        weights={'none':[.2126,.7152,.0722],'red':[.55,.4,.05],'yellow':[.35,.6,.05],'green':[.12,.82,.06]}[r.mono_filter]
        y=np.sum(a*np.array(weights,np.float32),axis=2)
        if r.film=='acros' and not official:y=y+.25*(y-.5)*y*(1-y)
        a=np.repeat(y[:,:,None],3,axis=2)
        if r.film=='sepia':a*=np.array([1.08,.96,.80],np.float32)
        a+=y[:,:,None]*(1-y[:,:,None])*np.array([r.mono_warm*.004-r.mono_green*.002,r.mono_green*.003,-r.mono_warm*.004-r.mono_green*.002],np.float32)
    scale=max(context.get('full_shape',a.shape)[:2])/1600
    if r.noise_reduction>-4:
        amount=(r.noise_reduction+4)/16
        smoothed=blur(a,max(.45,.65*scale));a*=1-amount;smoothed*=amount;a+=smoothed
    if r.smooth_skin!='off':
        mask=np.clip((a[:,:,0]-a[:,:,2])*5,0,1)*np.clip((a[:,:,1]-a[:,:,2])*5,0,1)
        mix=mask[:,:,None]*({'weak':.25,'strong':.5}[r.smooth_skin])
        a=a*(1-mix)+blur(a,max(.6,1.5*scale))*mix
    if r.clarity:
        base=(large_radius_blur(a,max(1,12*scale)) if output_transform
              else blur(a,max(1,12*scale)))
        base*=-1;base+=a;base*=r.clarity*.10;a+=base
    if r.sharpness:
        base=blur(a,max(.5,.75*scale));base*=-1;base+=a;base*=r.sharpness*.12;a+=base
    if r.grain!='off':
        apply_film_grain(a,r.grain,r.grain_size,
                         max(context.get('full_shape',a.shape)[:2])/6000,origin)
    np.clip(a,0,1,out=a)
    if not output_transform:return a
    return transform_output(a,r)


def transform_output(a,r):
    """Share crop/size geometry between the recipe and its RAW-base comparison."""
    h,w=a.shape[:2]
    cw,ch=int(w/r.digital_crop),int(h/r.digital_crop)
    if r.aspect!='original':
        rw,rh=map(int,r.aspect.split(':'));ratio=rw/rh
        if h>w:ratio=1/ratio
        if cw/ch>ratio:cw=round(ch*ratio)
        else:ch=round(cw/ratio)
    a=a[(h-ch)//2:(h-ch)//2+ch,(w-cw)//2:(w-cw)//2+cw]
    if r.image_size!='L':a=resize_float(a,round(max(a.shape[:2])*{'M':.7071,'S':.5}[r.image_size]))
    return a


def _integer_pixels(a,dtype):
    """Saturate final display samples before casting to an unsigned format."""
    # Lanczos crop/size alignment can overshoot after render's gamut clamp.
    # An unchecked cast wraps negative channels to white (and values > 1
    # to black), creating coloured speckles. Bound only the final output;
    # signed/HDR values earlier in the RAW pipeline must remain available.
    maximum=np.iinfo(dtype).max
    pixels=np.multiply(a,maximum)
    np.rint(pixels,out=pixels)
    np.clip(pixels,0,maximum,out=pixels)
    return pixels.astype(dtype)


def encode(a,r,preview=False,*,detail=False):
    icc=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    if r.color_space=='adobe_rgb' and not preview:
        from .platform_support import adobe_rgb_profile
        profile=adobe_rgb_profile()
        if profile is None:raise ValueError('Adobe RGB 1998 profile is missing from this computer. Install the profile or select sRGB.')
        # sRGB linear to Adobe RGB (1998), both D65; encode gamma 563/256.
        linear=srgb_decode(a)
        a=np.clip(np.einsum("...i,ij->...j",linear,np.array([[.7151626,0,0],[.2848374,1,.0411705],[0,0,.9588295]],np.float32)),0,1)**(256/563)
        icc=profile.read_bytes()
    buf=BytesIO()
    if preview or r.file_type=='jpeg':
        im=Image.fromarray(_integer_pixels(a,np.uint8))
        im.save(buf,'JPEG',quality=(96 if detail else 90) if preview else (96 if r.image_quality=='fine' else 82),
            subsampling=0 if preview and detail else -1,icc_profile=icc,
            comment=('KŌRA: '+('experimental Kodachrome 64; E-88 spectral approximation' if r.film=='kodachrome64' else 'official GFX ETERNA 55 LUT; uncalibrated photo adapter' if r.film in OFFICIAL_FILMS else 'independent artistic look')).encode())
        return buf.getvalue(),'image/jpeg'
    metadata={'renderer':'official-lut-photo-adapter-v1','recipe_response_revision':24,'official_lut':r.film if r.film in OFFICIAL_FILMS else None,'exact_fuji_render':False,'recipe':r.model_dump()}
    if r.film=='kodachrome64':
        from .kodachrome import model_info
        metadata.update(renderer='kodachrome64-spectral-v1',experimental=True,kodachrome=model_info())
    dtype=np.uint16 if r.file_type=='tiff16' else np.uint8
    tifffile.imwrite(buf,_integer_pixels(a,dtype),photometric='rgb',metadata=None,
        description=json.dumps(metadata),
        extratags=[(34675,'B',len(icc),icc,False)])
    return buf.getvalue(),'image/tiff'


def shooting_settings(meta, *, restore_wb_shift=False, legacy_tone=False):
    """Restore R/B only when the decoder removed them from this source."""
    import re
    values={'name':'File Settings (Partial)','wb':'camera','wb_red':0,'wb_blue':0}
    if not legacy_tone:
        values.update(highlight_tone=0,shadow_tone=0,highlights=0,whites=0,shadows=0,blacks=0)
    if restore_wb_shift and (shift:=fuji_shift(meta)) is not None:
        values.update(wb_red=shift[0],wb_blue=shift[1])
    films={'classic negative':'classic_negative','classic chrome':'classic_chrome','provia':'provia','velvia':'velvia','astia':'astia','eterna':'eterna','eterna bleach bypass':'eterna_bleach','reala ace':'reala_ace','nostalgic neg.':'nostalgic_negative','pro neg. std':'pro_neg_std','pro neg. hi':'pro_neg_hi'}
    # ExifTool's FujiFilm PrintConv uses these full MakerNote labels. A
    # missing match also biases the embedded-preview exposure estimate.
    films.update({'f0/standard (provia)':'provia',
                  'f1b/studio portrait smooth skin tone (astia)':'astia',
                  'f2/fujichrome (velvia)':'velvia','f4/velvia':'velvia',
                  'bleach bypass':'eterna_bleach','nostalgic neg':'nostalgic_negative'})
    film=str(meta.get('FilmMode','')).strip().lower()
    if film in films:values['film']=films[film]
    # ACROS/monochrome and its filter are encoded in Saturation, not FilmMode.
    mono=str(meta.get('Saturation','')).lower()
    if mono.startswith('acros') or mono.startswith('b&w') or mono=='none (b&w)':
        values['film']='acros' if mono.startswith('acros') else 'sepia' if 'sepia' in mono else 'monochrome'
        values['mono_filter']=next((c for c in ['red','yellow','green'] if c in mono),'none')
    for tag,key in [('HighlightTone','highlights'),('ShadowTone','shadows'),('Saturation','color'),('Sharpness','sharpness'),('NoiseReduction','noise_reduction'),('Clarity','clarity')]:
        text=str(meta.get(tag,''));match=re.match(r'^([+-]?\d+(?:\.\d+)?)',text)
        if match:
            v=float(match[1])
            if key in ('highlights','shadows'):
                if legacy_tone:v=round(v*(25 if key=='highlights' else -25))
                else:key='highlight_tone' if key=='highlights' else 'shadow_tone'
            candidate={**values,key:v}
            try:StudioRecipe(**candidate)
            except ValueError:continue
            values[key]=v
        elif text.lower()=='normal':values[key]=0
    for tag,key in [('GrainEffectRoughness','grain'),('ColorChromeEffect','color_chrome'),('ColorChromeFXBlue','fx_blue')]:
        val=str(meta.get(tag,'')).lower()
        if val in ['off','weak','strong']:values[key]=val
    size=str(meta.get('GrainEffectSize','')).lower()
    if size in ['small','large']:values['grain_size']=size
    dr=meta.get('DevelopmentDynamicRange')
    if dr in [100,200,400]:values['dynamic_range']=dr
    return values
