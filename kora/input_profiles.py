"""Common RAW input contract and camera-scoped normalization profiles.

A recognized extension is only an import candidate; LibRaw must decode the
actual camera/compression. None of these profiles claims Fuji colour matching.
"""
from dataclasses import dataclass
import numpy as np

RAW_EXTENSIONS=frozenset({'.raf','.dng','.cr2','.cr3','.crw','.nef','.nrw',
    '.arw','.sr2','.srf','.rw2','.orf','.ori','.pef','.ptx','.srw',
    '.3fr','.fff','.iiq','.rwl','.mos','.mrw','.kdc','.dcr','.erf','.mef','.raw'})

@dataclass(frozen=True)
class CameraInputProfile:
    key: str
    exposure_offset_ev: float
    floating_camera_rgb: bool
    label: str

# Leica mosaic DNGs benefit from the signed floating-point camera-matrix path.
# This is a decoding strategy, not a model-specific exposure calibration.
LEICA_DNG=CameraInputProfile('leica-dng-v1',0.,True,
                             'Leica DNG · floating color conversion')
LEICA_Q3_43=CameraInputProfile('leica-q3-43-reference-v1',0.,True,
                              'Leica Q3 43 · reference color adjustment')
# Small working-space white-point refinement from one daylight Leica/X-M5
# pair. The pair's exposure offset is deliberately NOT part of this profile.
# Other cameras and other DNG models have not been measured by this experiment.
Q3_43_REFERENCE_GAINS=np.array([1.0018982841,1.,.9798716044],np.float32)

def camera_profile(metadata):
    make=str(metadata.get('Make','')).strip().upper()
    model=' '.join(str(metadata.get('Model','')).strip().upper().split())
    if make.startswith('LEICA'):
        if model in ('LEICA Q3 43','Q3 43'):return LEICA_Q3_43
        return LEICA_DNG
    return None


def apply_input_color(pixels,profile_key):
    """Apply the measured input refinement without clipping signed RAW data."""
    if profile_key!=LEICA_Q3_43.key:return pixels
    return np.asarray(pixels,dtype=np.float32)*Q3_43_REFERENCE_GAINS


def validate_linear_input(pixels):
    """Enforce the shared representation without clipping RAW headroom."""
    a=np.asarray(pixels,dtype=np.float32)
    if a.ndim!=3 or a.shape[-1]!=3 or min(a.shape[:2])==0 or not np.isfinite(a).all():
        raise ValueError('Invalid RAW input: finite three-channel linear RGB is required.')
    return a


def normalization_details(metadata,suffix,exposure):
    profile=camera_profile(metadata) if suffix.lower()=='.dng' else None
    is_fuji=suffix.lower()=='.raf'
    matched=exposure.get('reference_matched',False)
    wb=exposure.get('white_balance',{})
    wb_label=('Fuji · camera WB without R/B shift' if wb.get('shift_removed') else
              'Fuji · camera WB (shift not removed)' if wb.get('warning') else 'Fuji · camera WB')
    return {'version':1,'working_space':'linear sRGB','white_point':'D65',
        'dtype':'float32','display_clipping':False,'white_balance':wb.get('basis','camera at decode'),
        'color_conversion':'LibRaw camera conversion',
        'profile':profile.key if profile else 'fuji-reference' if is_fuji else 'generic-libraw',
        'label':profile.label if profile else wb_label if is_fuji else 'Generic input · uncalibrated',
        'exposure_method':'fixed camera offset + metadata' if profile and profile.exposure_offset_ev else
            'embedded preview luminance estimate + metadata' if matched else 'metadata only',
        'exposure_is_absolute_calibration':False,'fuji_color_calibrated':False,
        'embedded_pixels_used_in_output':False,
        'signed_camera_conversion':bool(profile and profile.floating_camera_rgb),
        'color_refinement':{'reference':'one Q3 43 / X-M5 daylight pair',
            'working_rgb_gains':Q3_43_REFERENCE_GAINS.tolist(),
            'cross_scene_color_validation':False,'exposure_offset_applied':False}
            if profile==LEICA_Q3_43 else None,
        'make':str(metadata.get('Make','')),'model':str(metadata.get('Model',''))}
