//! Reader for the official 65-grid `.cube` tables.
use std::fmt;
use std::path::Path;

pub const GRID: usize = 65;

/// A 3D LUT indexed `[blue][green][red]`, as `.cube` enumerates red fastest.
pub struct Lut3d {
    data: Vec<[f32; 3]>,
}

#[derive(Debug)]
pub struct LutError(String);

impl fmt::Display for LutError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for LutError {}

impl Lut3d {
    pub fn load(path: &Path) -> Result<Self, LutError> {
        let text = std::fs::read_to_string(path)
            .map_err(|e| LutError(format!("cannot read {}: {e}", path.display())))?;
        Self::parse(&text)
    }

    pub fn parse(text: &str) -> Result<Self, LutError> {
        if !text.lines().any(|line| line.trim() == "LUT_3D_SIZE 65") {
            return Err(LutError("unexpected LUT grid".into()));
        }
        let mut data = Vec::with_capacity(GRID * GRID * GRID);
        for line in text.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') || line.starts_with("LUT_") {
                continue;
            }
            let mut values = line.split_whitespace().map(str::parse::<f32>);
            let mut next = || -> Result<f32, LutError> {
                match values.next() {
                    Some(Ok(v)) if v.is_finite() => Ok(v),
                    _ => Err(LutError(format!("invalid LUT row: {line}"))),
                }
            };
            data.push([next()?, next()?, next()?]);
        }
        if data.len() != GRID * GRID * GRID {
            return Err(LutError(format!("expected {} rows, found {}", GRID * GRID * GRID, data.len())));
        }
        Ok(Self { data })
    }

    #[inline(always)]
    fn at(&self, b: usize, g: usize, r: usize) -> [f32; 3] {
        self.data[(b * GRID + g) * GRID + r]
    }

    /// Trilinear lookup of RGB in 0..=1, matching scipy `map_coordinates`
    /// with `order=1, mode='nearest', prefilter=False`.
    #[inline(always)]
    pub fn sample(&self, rgb: [f32; 3]) -> [f32; 3] {
        let last = (GRID - 1) as f32;
        let split = |v: f32| {
            let c = v.clamp(0.0, 1.0) * last;
            let i = (c.floor() as usize).min(GRID - 2);
            (i, c - i as f32)
        };
        let (r0, tr) = split(rgb[0]);
        let (g0, tg) = split(rgb[1]);
        let (b0, tb) = split(rgb[2]);
        let mut out = [0f32; 3];
        for (db, wb) in [(0, 1.0 - tb), (1, tb)] {
            for (dg, wg) in [(0, 1.0 - tg), (1, tg)] {
                for (dr, wr) in [(0, 1.0 - tr), (1, tr)] {
                    let w = wb * wg * wr;
                    let v = self.at(b0 + db, g0 + dg, r0 + dr);
                    out[0] += w * v[0];
                    out[1] += w * v[1];
                    out[2] += w * v[2];
                }
            }
        }
        out
    }
}
