# KŌRA GUI

Start the application with `Launch Kora.command`, or run `python -m kora gui --port 8766`. Open the complete link printed in the terminal; its session fragment grants access to the local server. If port 8766 is occupied, the terminal prints a new address on an available port.

The ten films marked **Fuji LUT** use official GFX ETERNA 55 tables. Other films remain independent interpretations. See the [pipeline and limits](OFFICIAL_LUT_STUDIO.md).

## Workflow

1. Click **Open Folder**. Select Home, Desktop, Pictures, Documents, Downloads, or a configured start folder. Navigate with the folder list, parent button, or breadcrumbs. A manual path field remains available under **Enter a folder path**.
2. Leave **Include subfolders** enabled to build a recursive library, then click **Choose This Folder**. Up to 5,000 compatible RAW files are shown and the first local photograph opens automatically.
3. PROVIA / Standard is the initial film simulation. Changing a control updates the preview after a short delay. **Image ready** confirms that the visible detail has finished loading.
4. Every photograph keeps its own current recipe. The bottom carousel shows embedded RAW thumbnails: a white **VIEWING** badge identifies the photo on screen, while a gold check identifies every photo in the editing group. Click a thumbnail to work on it alone, or click its selection circle to include or remove it from the group. **Keep current only** clears a group. Selected thumbnails receive the same subsequent adjustments while preserving their other existing values. Use C1–C7 or JSON to save named alternatives.
5. **View Without Film** compares the independent render with the same RAW development without film simulation or recipe adjustments. It is not a comparison with an in-camera Fuji JPEG.
6. Select the output options and click **Export Image**. With several JPEG photos selected, the button exports all of them—each with its current recipe—in one ZIP archive. A single photo can still be exported as JPEG or TIFF. Export performs a full-resolution decode before applying output cropping or resizing.

The library reads local files in place. Individual file imports are copied to a temporary directory and removed at shutdown. Originals remain untouched.

## Photo workspace and zoom

- **Library** and **Settings** toggle each side panel. **Photo View** hides both; **Show Panels** restores them. Panel preferences are kept in browser storage.
- The mouse wheel and **− / +** buttons control zoom. The menu offers Fit, 50%, 100%, 200%, and 400%. Drag a magnified image to pan.
- Double-click the image to alternate between Fit and 100%. Fit recalculates after the window or panel layout changes.
- Zoom is retained while recipe settings render and resets when another photograph opens.

Recipe changes first use a cached 1,800-pixel linear preview to keep the controls responsive. Every view, including **Fit**, then progressively loads detailed regions from the full-resolution RAW at the resolution required by the display. Wait for **Image ready** to judge sharpness. At **100%**, one developed image pixel maps to one physical screen pixel, including on Retina. Visible detail stays in place while panning or changing zoom; cached regions are reused. The comparison without film receives the same refinement and keeps the recipe's crop. Export always uses the full-resolution RAW. See [display validation and limits](DISPLAY_0.2.33.md).

## Output resolution

With **Image Size: L**, **Image Aspect: Original**, and **Digital Teleconverter: Off**, the exported JPEG or TIFF has the same width and height as the full-resolution developed RAW array. **JPEG Quality: Fine** changes JPEG compression only and never resizes the image.

Selecting another aspect ratio or a digital teleconverter setting crops the output. Some automatic lens profiles can change the usable boundary. The dimensions returned by LibRaw can also exclude masked sensor margins and therefore differ slightly from nominal camera specifications or an in-camera JPEG.

## Available controls

Film simulation, exposure in one-third EV steps, DR100/200/400, D Range Priority, white balance and R/B shifts, Highlights, Whites, Shadows, Blacks, Color, Sharpness, Noise Reduction, Clarity, Grain Effect and size, Color Chrome Effect, Color Chrome FX Blue, monochrome filters and toning, Smooth Skin Effect, crop and aspect ratio, L/M/S sizes, Fine/Normal JPEG quality, JPEG/TIFF 8-bit/TIFF 16-bit, and sRGB/Adobe RGB output.

The four tonal controls use the familiar −100…+100 photo-editor convention. Negative Highlights and Whites recover bright regions; positive Shadows and Blacks open dark regions. Whites and Blacks target narrower endpoints than Highlights and Shadows. Monotonic scene-linear curves retain RAW headroom and RGB ratios, followed in recovery directions by selective, edge-aware restoration of local detail. This can strengthen structure that remains in the RAW, but cannot recreate sensor samples clipped at capture. The response is designed to feel similar to a professional RAW editor; it is an independent implementation, not Capture One code or a calibrated Capture One match.

Recipes saved with schema version 1 are migrated automatically: the former Fuji-style Highlight Tone and Shadow Tone values are converted to the new scale, while Whites and Blacks start at zero.

Color, texture, and dynamic-range operations are independent approximations. A Fuji recipe with the same numeric values does not guarantee the same output as X RAW STUDIO.

## White balance grid

The 19 × 19 grid adjusts Red and Blue from −9 to +9. Positive Red is to the right and positive Blue is upward. Click or drag the marker, or use the arrow keys and Home to center it. **Center R/B** resets only these two shifts.

The grid and sliders remain synchronized after Undo, Redo, JSON load, or C1–C7 recall. One drag counts as one undo action. Shifts are applied before the LUT in both preview and export. Their numerical response belongs to this independent adapter and is not a Fuji calibration.

## Lens corrections

Distortion and vignetting can be enabled separately with **Automatic Profile**. The status text identifies the detected source and reports which corrections are available. Both settings are off by default. See [multi-camera coverage, tests, and input normalization](OPTICS_AND_NORMALIZATION.md).

## Explicit differences from X RAW STUDIO

- Fuji proprietary Lens Modulation Optimizer and multi-exposure HDR are visible but unavailable.
- Digital Teleconverter performs a center crop without Fuji super-resolution.
- Shooting Settings imports only unambiguous metadata. White-balance shifts reset because camera white balance was already used during decoding. Missing values are not reconstructed.
- Custom WB C1/C2/C3, HEIF, native FP profiles, and histogram tools are not implemented. Batch export currently supports JPEG only.
- Adobe RGB requires the macOS system profile; the screen preview remains sRGB.

The GUI can develop and export photographs. Complete X RAW STUDIO parity and exact Fujifilm color rendering have not been achieved.
