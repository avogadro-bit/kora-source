//! Prototype pixel core for KORA.
//!
//! Mirrors `kora/official_luts.py` (linear sRGB -> F-Gamut -> F-Log2 -> official
//! 65-grid LUT -> Rec.709 gamma 2.2 display -> sRGB) so the two implementations
//! can be compared pixel for pixel. Not a Fujifilm image engine.

pub mod lut;
pub mod npy;
pub mod official;
