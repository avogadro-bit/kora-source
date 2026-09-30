# Grain calibration and DR preview artifacts

Historical measurements and implementation notes. See [X-M5 measurements](XM5_CALIBRATION.md) for the 0.2.27 grain update. The current grain revision
is documented in [Grain 0.2.23](GRAIN_0.2.23.md).

The studio's grain remains an independent approximation. Fujifilm documents
`ROUGHNESS` (`WEAK`/`STRONG`) and `SIZE` (`SMALL`/`LARGE`) as separate controls,
and describes the effect as a controlled amount of random noise:

- <https://fujifilm-dsc.com/en-int/manual/x100vi/menu_shooting/image_quality_setting/>
- <https://www.fujifilm-x.com/en-gb/learning-centre/color-chrome-and-film-grain-effects/>

The official public 862 × 575 pixel with/without pair was measured as a useful
visual reference, not as proof of the camera's internal algorithm. Its RGB
difference is strongly correlated across channels (0.979–0.984), its luminance
standard deviation is about 0.041 through most midtones, and adjacent
luminance differences have a small negative correlation (about -0.11). This
supports monochrome, high-frequency, band-pass noise rather than the previous
low-pass Gaussian texture. The public example does not identify every camera
setting, so the Weak/Strong amplitudes and Small/Large bandwidths are still
approximations.

The white DR preview points were independently reproduced on Leica
`L1005503.DNG`: DR200/DR400 produced 30–35 isolated white pixels in the
1,600-pixel preview and none in the full-resolution result reduced to the same
size. They were negative, signed out-of-gamut samples at the image boundary.
`dynamic_range_compress` divided negative luminance by a positive epsilon,
inverting those samples to very large positive values. Signed non-positive
luminance now passes through DR compression without inversion.
