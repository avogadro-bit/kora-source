# Highlights and Whites — 0.2.25

The previous serial exposure tails evaluated Whites after Highlights had
already compressed the image. At Highlights −100, even a linear input of 2.0
was below the Whites pivot, so moving Whites had no effect. Increasing the
old coefficients could not fix this selection problem.

The two controls now shape contrast on the original exposure axis. Integrating
an everywhere-positive derivative keeps the global curve monotonic for all
combinations, including opposite settings. Highlights start above middle gray;
Whites act on a narrower upper range starting at about 0.61 linear luminance.
A gentle response near zero and stronger endpoints provide fine small edits
and greater reduction at the end of the range. No HDR clipping occurs here.

To retain fine texture under strong reductions, the renderer applies the curve
to an edge-aware log-luminance base before the film LUT. The difference from
the global curve is limited to a quarter stop and fades out below highlights.
Local filters use resolution-scaled radii and bounded row halos; viewport tiles
use the same photographic scale as full exports. This does not sharpen the
post-film white shoulder or alter camera-channel reconstruction.

The GUI accepts Highlights/Whites in tenths, including typed values. Arrow keys
adjust by 0.1; Shift + arrows by 1. Undo, linked edits, saved studio recipes and
D Range Priority retain their usual behavior. Native research recipes retain
integer-only tone fields. Studio recipe revision is 17; all-zero tone settings
retain the previous rendering. Existing nonzero settings intentionally render
with the new response and may need adjustment.

Validation covers independent Whites action at Highlights −100, fractional
round trips and bounds, smooth small steps, HDR gradation, opposite-setting
monotonicity, texture retention, strong edges and halo-tile consistency. Local
real-image checks include the previous three clipped-sky regressions and the
warm dog photograph. Private source photographs stay outside release packages.

This is an independent tone-mapping model, not Capture One's algorithm or a
claim of matching its latitude on every RAW. The supplied Capture One screenshot
is a qualitative reference; it is insufficient for calibrated equivalence.
Fully saturated sensor values cannot yield real missing detail.

Reference for the intended distinction between broad highlights and brightest
whites: [Capture One HDR tool overview](https://support.captureone.com/hc/en-us/articles/360002610558-The-High-Dynamic-Range-tool-overview).
