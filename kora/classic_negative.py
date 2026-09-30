"""Small chromatic refinement of the Classic Negative photo adaptation.

Fitted on two X-M5 scenes, checked on three others. Keep the LUT's luminance
and neutral axis: fitting a global exposure/contrast residual did not transfer
reliably between scenes. This remains an independent approximation.
"""
import numpy as np
from .official_luts import run_parallel_rows


# CIE XYZ, D65, 2-degree observer. Row-vector RGB transforms.
_TO_XYZ=np.array([[.412453,.212671,.019334],
                  [.357580,.715160,.119193],
                  [.180423,.072169,.950227]],np.float32)
_FROM_XYZ=np.linalg.inv(_TO_XYZ).astype(np.float32)
_WHITE=np.array([.95047,1.,1.08883],np.float32)
_WEIGHTS=_TO_XYZ[:,1]
_COEFFICIENTS=np.array([
    [5.56736722,.62524086], [.07299924,-22.80638201],
    [-5.01027981,4.23409892], [-5.97664499,7.02742716],
],np.float32)


def refine_classic_negative(rgb):
    """Refine display-sRGB colour, preserving scene-independent luminance.

CIELAB L* is fixed. If the new colour leaves sRGB, reduce chroma along a
constant-luminance line instead of clipping each channel. Each row band is
independent, so full renders and viewport tiles use exactly the same mapping.
"""
    output=np.empty_like(rgb,dtype=np.float32)
    def process(start,stop):
        source=rgb[start:stop]
        linear=np.where(source<=.04045,source/12.92,
                        ((np.maximum(source,0)+.055)/1.055)**2.4)
        xyz=np.einsum('...i,ij->...j',linear,_TO_XYZ)
        normalized=xyz/_WHITE
        epsilon=(6/29)**3
        f=np.where(normalized>epsilon,np.cbrt(normalized),
                   normalized/(3*(6/29)**2)+4/29)
        fx,fy,fz=np.moveaxis(f,-1,0)
        light=(116*fy-16)/100
        ca=5*(fx-fy);cb=2*(fy-fz)  # a*/100, b*/100
        delta=(ca[...,None]*(_COEFFICIENTS[0]+light[...,None]*_COEFFICIENTS[2])
               +cb[...,None]*(_COEFFICIENTS[1]+light[...,None]*_COEFFICIENTS[3]))
        delta*=np.minimum(1,15/np.maximum(np.max(abs(delta),axis=-1,keepdims=True),1e-8))
        refined_f=np.stack((fx+delta[...,0]/500,fy,fz-delta[...,1]/200),axis=-1)
        refined_xyz=np.where(refined_f>6/29,refined_f**3,
                             3*(6/29)**2*(refined_f-4/29))*_WHITE
        refined=np.einsum('...i,ij->...j',refined_xyz,_FROM_XYZ)
        luminance=xyz[...,1:2]
        chroma=refined-luminance
        scale=np.minimum(1,np.min(np.where(chroma>0,
            (1-luminance)/np.maximum(chroma,1e-8),
            luminance/np.maximum(-chroma,1e-8)),axis=-1,keepdims=True))
        refined=np.clip(luminance+np.maximum(scale,0)*chroma,0,1)
        encoded=np.where(refined<=.0031308,refined*12.92,
                         1.055*refined**(1/2.4)-.055)
        # Exact identity for achromatic inputs, including black and white.
        neutral=(source.max(-1)-source.min(-1))<1e-7
        encoded[neutral]=source[neutral]
        output[start:stop]=np.clip(encoded,0,1)
    run_parallel_rows(len(rgb),process,block_rows=128)
    return output
