# Highlight colour regression — 0.2.24

The 0.2.22 recovery introduced large cyan/magenta regions on partly clipped
Leica skies. It remained in 0.2.23. Nearest-neighbour propagation of camera
channel ratios used dark coloured foreground objects as donors, creating
Voronoi-shaped colour boundaries. Testing only a bright warm subject did not
cover this failure. Grain is independent and unchanged by this correction.

Recovery now rejects dark donors relative to the affected channel's clipped
level, trims extreme ratios, and uses normalized Gaussian convolution at four
scales. Local estimates take over smoothly according to donor support, with a
robust broad fallback. A 600-pixel reference grid bounds computation. Ratios,
not image texture, are propagated; surviving channels remain untouched.

A continuous bounded prior also prevents the estimate from dropping back to
the original clipped value when the last reliable anchor disappears. Pixels
with all channels clipped are still neutralized after the camera matrix.
No detail can be recovered where every sensor channel is saturated. Estimated
colour is uncertain without nearby bright unsaturated samples; this remains
an independent heuristic, not a calibrated Capture One or Fuji implementation.

Validation:

- 213 unit tests pass. Added sky/foreground contamination, continuity across
  last-channel saturation, and preview/full-scale consistency cases.
- Both new contamination and last-anchor regression tests fail against the
  0.2.23 implementation and pass with this correction.
- Local Leica Q3 43 originals L1003570, L1003314 and L1003412 reproduce the
  reported polygons. Checked at neutral Highlights/Whites and at −100/−100,
  using PROVIA and Classic Chrome as in the reported examples.
- L1008308 is retained as the warm-highlight regression case at −100/−100.
- Private photos and generated comparisons are excluded from source packages.

The decode change increments recipe response revision to 16. Restart KŌRA
after installing the new build to discard previously decoded images.
