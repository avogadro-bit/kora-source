# Kodachrome 64 validation — 0.2.42

Checked locally on 8 October 2026. These checks establish implementation
agreement and application behavior, not fidelity to physical Kodachrome.

- Python: 292 tests passed, no skipped tests; includes seven dedicated K64 tests.
- JavaScript: 17 tests passed, including film selection and legacy recipe behavior.
- Direct spectral reference: 160 colors × seven Push / Pull offsets from −3 to +3.
  Maximum encoded-sRGB channel error: 0.002295 (less than 0.59 of an 8-bit code
  value); highest per-exposure 99th percentile: 0.000881.
- DNG L1008086, 9536 × 6344: 192 directly reconstructed spectral checks,
  maximum channel error 0.000507. Core render about 2.73 seconds on this Mac,
  excluding RAW decoding (8.95 seconds) and encoding. TIFF16 dimensions and ICC
  verified. Detail region agrees exactly with the same full-render region.
- DNG L1003970, 1800 × 1197 preview: 192 direct checks, maximum error 0.000776;
  about 0.12 seconds for the core render. Detail region agrees exactly.
- Both source DNG SHA-256 checksums were identical before and after validation.
- The packaged Mac executable successfully served the new recipe, interactive
  and full-RAW display previews, a 512 × 512 source-resolution tile and a full
  9536 × 6344 JPEG export with sRGB ICC and the experimental-film comment.
- The browser interface was checked with the film selected, Fit view and 100%
  detail. A screenshot is supplied with the local validation artifacts.
- All 139 packaged native binaries passed the macOS 14 / arm64 compatibility
  audit; local ad-hoc code-signature verification passed. This is a binary
  compatibility audit, not a test on every macOS version or another Mac.
- The wheel and source archive contain the model, exact-input test fixture,
  reconstruction sources, spectral data and attribution. They contain no
  personal photographs or Fujifilm LUT files.

Model SHA-256:
`032471d4805a6d22da127d98bc8ab422cf3d4159a745ed28dd8396ce2b01da03`

Reproduce numerical checks with `scripts/validate_kodachrome.py`. For a local
RAW, use `scripts/validate_kodachrome_raw.py INPUT.DNG --output OUTPUT_DIR`,
adding `--full` for full resolution. It checks hashes, spectral samples and a
detail tile and writes TIFF16/JPEG results in the requested output directory.
The numeric thresholds do not bound errors against unseen physical film or
all possible RGB inputs. Signed/HDR behavior uses the documented extension.
