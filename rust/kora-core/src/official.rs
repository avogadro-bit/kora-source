//! Official LUT photo adapter, one fused pass per pixel.
use crate::lut::Lut3d;
use rayon::prelude::*;

/// Linear sRGB / BT.709 D65 to F-Gamut (BT.2020 primaries), row vectors.
const TO_F_GAMUT: [[f32; 3]; 3] = [
    [0.627403896, 0.069097289, 0.016391439],
    [0.329283038, 0.919540395, 0.088013308],
    [0.043313066, 0.011362316, 0.895595253],
];
const LUT_DISPLAY_GAMMA: f32 = 2.2;

#[inline(always)]
fn flog2_encode(x: f32) -> f32 {
    let x = x.max(0.0);
    if x < 0.000889 {
        8.799461 * x + 0.092864
    } else {
        0.245281 * (5.555556 * x + 0.064829).log10() + 0.384316
    }
}

#[inline(always)]
fn srgb_encode(x: f32) -> f32 {
    if x <= 0.0031308 {
        x * 12.92
    } else {
        1.055 * x.powf(1.0 / 2.4) - 0.055
    }
}

#[inline(always)]
pub fn apply_pixel(lut: &Lut3d, p: [f32; 3]) -> [f32; 3] {
    let mut log = [0f32; 3];
    for (j, value) in log.iter_mut().enumerate() {
        let linear = p[0] * TO_F_GAMUT[0][j] + p[1] * TO_F_GAMUT[1][j] + p[2] * TO_F_GAMUT[2][j];
        *value = flog2_encode(linear);
    }
    let video = lut.sample(log);
    video.map(|v| srgb_encode(v.max(0.0).powf(LUT_DISPLAY_GAMMA)).clamp(0.0, 1.0))
}

/// Apply the film to interleaved linear RGB (`len % 3 == 0`) in parallel.
pub fn apply_official(lut: &Lut3d, linear: &[f32], out: &mut [f32]) {
    assert_eq!(linear.len(), out.len());
    assert_eq!(linear.len() % 3, 0);
    const CHUNK: usize = 3 * 8192;
    out.par_chunks_mut(CHUNK)
        .zip(linear.par_chunks(CHUNK))
        .for_each(|(dst, src)| {
            for (d, s) in dst.chunks_exact_mut(3).zip(src.chunks_exact(3)) {
                d.copy_from_slice(&apply_pixel(lut, [s[0], s[1], s[2]]));
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;

    fn identity_cube() -> String {
        let mut text = String::from("LUT_3D_SIZE 65\n");
        for b in 0..65 {
            for g in 0..65 {
                for r in 0..65 {
                    text += &format!("{} {} {}\n", r as f32 / 64.0, g as f32 / 64.0, b as f32 / 64.0);
                }
            }
        }
        text
    }

    #[test]
    fn identity_lut_interpolates_exactly() {
        let lut = Lut3d::parse(&identity_cube()).unwrap();
        for rgb in [[0.0, 0.5, 1.0], [0.123, 0.456, 0.789], [1.0, 1.0, 1.0]] {
            let v = lut.sample(rgb);
            for c in 0..3 {
                assert!((v[c] - rgb[c]).abs() < 1e-6, "{rgb:?} -> {v:?}");
            }
        }
    }

    #[test]
    fn flog2_is_continuous_at_the_knee() {
        let below = flog2_encode(0.000889 - 1e-7);
        let above = flog2_encode(0.000889);
        assert!((below - above).abs() < 1e-4);
    }

    #[test]
    fn output_is_display_bounded() {
        let lut = Lut3d::parse(&identity_cube()).unwrap();
        for p in [[-1.0, 0.0, 0.0], [8.0, 8.0, 8.0], [0.18, 0.18, 0.18]] {
            for v in apply_pixel(&lut, p) {
                assert!((0.0..=1.0).contains(&v));
            }
        }
    }
}
