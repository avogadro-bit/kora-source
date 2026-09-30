# 0.2.23 — Fuji-inspired grain, revised scale and sampling

The requested target is the grain effect used alongside Fujifilm film
simulations. This replaces the large, cloudy texture seen in high-resolution
Kora exports while retaining Weak/Strong and Small/Large as separate controls.
The preceding highlight recovery fixes remain included.

## Reference and limits

Fujifilm's [with/without demonstration](https://www.fujifilm-x.com/en-gb/learning-centre/color-chrome-and-film-grain-effects/)
and [X100VI manual](https://fujifilm-dsc.com/en-int/manual/x100vi/menu_shooting/image_quality_setting/)
provide the reference appearance and control semantics. The public pair is
862 × 575 pixels. Its full recipe, crop/resize history and grain size setting
are unknown, so it cannot establish an exact camera algorithm or calibration.

On that pair, mean-RGB residual standard deviation is about 0.04195 for
display luminances 0.1–0.75, and horizontal adjacent-pixel correlation is
about −0.116. The revised fine reference texture targets these two statistics:
near-achromatic, fine high-frequency roughness rather than broad blurred noise.
These measures describe one example, not all Fuji simulations or ISO settings.
Weak strength, Large size and the 6000-pixel reference plane remain explicit
independent choices. ACROS's camera-native ISO-dependent grain is not modeled.

## Changes

- Grain occupies a fixed photographic coordinate plane with a 6000-pixel long
  edge. Previously, the filters were enlarged relative to a 1600-pixel image:
  a 9536-pixel export magnified their radii by almost six times.
- Small uses finer spatial structure; Large increases correlation length.
  The two sizes use fixed variance normalization, independent of output size.
- Weak/Strong vary amplitude (0.022/0.042), not particle size. Strength is
  mostly constant across usable tones, fading smoothly at black and white.
- RGB receives luminance roughness with hue-preserving gamut compression at
  the boundary. Pure black and white remain unchanged; there is no chroma noise.
- Grain is anchored to absolute image coordinates. Tiles receive real neighbour
  samples on all sides, eliminating crop-edge seams and changes while panning.
- Reduced views integrate subpixel samples from that same plane. Half- and
  quarter-size grain fields match box reductions of the reference field exactly.
  Below 12.5% scale an approximate Gaussian footprint limits sampling cost.
- Generation remains parallel in bounded row bands. No photo detail is blurred
  to produce the texture. Grain Off bypasses the new processing entirely.

## Validation

Tests cover repeatability, tile continuity at fractional scales, reduced-view
integration, independent size/strength, tonal endpoints, saturated colours and
render integration. A local 60 MP Leica DNG supplies the photographic comparison;
the source and comparison images are excluded from distribution. Existing
recipes keep their values but grain-enabled recipes intentionally render
differently. Restart the app to clear old render caches.
