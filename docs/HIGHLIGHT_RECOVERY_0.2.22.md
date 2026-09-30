# Highlight recovery — 0.2.22

Historical validation was insufficient: broad skies regressed in 0.2.22/0.2.23.
See [the 0.2.24 correction](HIGHLIGHT_REGRESSION_0.2.24.md).

Reducing Highlights and Whites on Leica Bayer DNGs could expose gray islands
on bright coloured subjects. Two saturated green sensels in a Bayer cell were
counted as two lost colours, so the decoder neutralized surviving red and blue
information. A display-stage brightness safeguard then blended bright pixels
back toward the unadjusted white shoulder, undoing recovery.

The floating camera decoder now tracks saturation separately for red, green,
and blue. It estimates only affected camera channels from surviving channels
and nearby unsaturated colour ratios before the camera matrix. The two green
sites contribute to one channel. Only saturation of all three distinct colours
requests neutralization. The source file is never modified.

The display-stage return to baseline white has been removed. Film hue
stabilization still preserves the baseline hue below the shoulder, but blends
smoothly toward the adjusted RAW rendering as the reference approaches white.
It no longer forces recovered coloured highlights to inherit clipped white.

This is an independent reconstruction heuristic, not Capture One's processing
or a measurement of missing sensor colour. Fully saturated regions contain no
recoverable texture. Colour ratios can be uncertain across material boundaries.
Other input paths retain their existing decoder; the film-shoulder change
applies to all official film looks when tonal adjustments are active.

Validation:

- 206 unit tests pass, including synthetic green-channel saturation, intact
  channel preservation, all-channel saturation, continuous film-shoulder colour,
  and the existing input, rendering, export, GUI and research tests.
- A local Leica Q3 43 DNG was decoded, rendered with PROVIA, Highlights −100 and
  Whites −100, and exported at 9536 × 6344. Visual inspection confirms removal
  of the reported gray patches on the bright face and neck.
- Reduced preview versus downsampled full render: mean absolute RGB difference
  0.00197 on a 0–1 scale; 99th percentile 0.01563. Different demosaicing and
  resampling mean previews are not pixel-identical to exports.
- The supplied Capture One screenshot is a qualitative reference, not a
  colour-calibrated or pixel-aligned comparison. The original Kora export's
  complete recipe was not supplied.

Private test photographs and generated comparisons remain outside source
packages. Reopen the app to discard decoded-image caches from older versions.
