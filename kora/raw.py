"""RAW input diagnostics and neutral test assets, not Fuji rendering."""
from collections import Counter
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time

import numpy as np
from PIL import Image, ImageCms
import rawpy
from .external_tools import find_exiftool


def local_file(path: Path) -> bool:
    st = path.stat()
    # Do not trigger downloads of OneDrive/cloud placeholders on Windows.
    if getattr(st, 'st_file_attributes', 0) & (0x1000 | 0x40000 | 0x400000):
        return False
    # macOS SF_DATALESS=0x40000000. Blocks are a secondary heuristic only.
    return not bool(getattr(st, "st_flags", 0) & 0x40000000) and (getattr(st, "st_blocks", 1) > 0 or st.st_size == 0)


def require_local(path: Path):
    if not local_file(path):
        raise ValueError(f"Cloud file is not downloaded: {path}. Make it available offline before reading it.")


def sha256(path: Path) -> str:
    require_local(path)
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def inventory(roots: list[Path]) -> dict:
    files = []
    for root in roots:
        if not root.is_dir():
            raise ValueError(f"Folder not found: {root}")
        for path in sorted(root.rglob("*")):
            if path.suffix.lower() not in {".raf", ".dng"} or not path.is_file():
                continue
            sidecars = [str(p) for p in path.parent.glob(path.stem + ".*") if p.suffix.lower() in {".jpg", ".jpeg", ".fp1", ".fp2", ".fp3", ".fp4"}]
            files.append({"path": str(path.resolve()), "format": path.suffix.lower()[1:], "bytes": path.stat().st_size, "local": local_file(path), "sidecars": sorted(sidecars)})
    return {"counts": dict(Counter(f["format"] for f in files)), "local_counts": dict(Counter(f["format"] for f in files if f["local"])), "files": files}


def normalize_exif(data):
    """Prefer precise Fuji MakerNotes over lossy standard EXIF duplicates."""
    result={k.split(':')[-1]:v for k,v in data.items()}
    result.update({k.split(':')[-1]:v for k,v in data.items() if k.startswith('FujiFilm:')})
    result.pop('SourceFile',None)
    return result


def exif(path: Path) -> dict:
    require_local(path)
    executable = find_exiftool()
    if not executable:
        if path.suffix.lower() == '.dng':
            return dng_input_metadata(path)
        return {"metadata_available": False, "reason": "ExifTool missing"}
    tags = ["BaselineExposure", "Make", "Model", "RawImageFullSize", "ImageWidth", "ImageHeight", "ISO", "ExposureTime", "FNumber", "FilmMode", "WhiteBalance", "WhiteBalanceFineTune", "WB_GRBLevelsAuto", "WB_GRGBLevelsAuto", "DynamicRange", "DevelopmentDynamicRange", "HighlightTone", "ShadowTone", "Saturation", "Sharpness", "NoiseReduction", "GrainEffectRoughness", "GrainEffectSize", "ColorChromeEffect", "ColorChromeFXBlue", "Clarity", "DNGVersion", "PhotometricInterpretation", "Software", "ColorMatrix1", "ColorMatrix2", "ForwardMatrix1", "ForwardMatrix2", "AsShotNeutral", "CFARepeatPatternDim", "CFAPattern2", "BlackLevel", "WhiteLevel", "CalibrationIlluminant1", "CalibrationIlluminant2"]
    result = subprocess.run([executable, "-j", "-G1", "-a", *["-" + t for t in tags], str(path)], capture_output=True, text=True, check=True, timeout=20,
                            creationflags=0x08000000 if sys.platform == 'win32' else 0)
    data = json.loads(result.stdout)[0]
    return normalize_exif(data)


def dng_input_metadata(path: Path) -> dict:
    """Read the input profile contract without an external executable.

    Only read TIFF tags, never raster data. ExifTool still supplies the richer
    shooting and lens metadata when available.
    """
    import tifffile
    result = {"metadata_available": False, "reason": "ExifTool missing"}
    try:
        with tifffile.TiffFile(path) as source:
            page = source.pages[0]
            for code, name in ((271, 'Make'), (272, 'Model'), (50730, 'BaselineExposure')):
                tag = page.tags.get(code)
                if tag is None:
                    continue
                value = tag.value
                if code == 50730:
                    if isinstance(value, tuple):
                        numerator, denominator = value
                        value = numerator / denominator
                    value = float(value)
                    if not np.isfinite(value):
                        continue
                result[name] = value
    except (OSError, ValueError, IndexError, ZeroDivisionError):
        return result
    if 'Make' in result and 'Model' in result:
        result.update(metadata_available=True, metadata_source='DNG tags',
                      reason='Basic DNG metadata; ExifTool unavailable')
    return result


def probe(path: Path) -> dict:
    require_local(path)
    started = time.monotonic()
    with rawpy.imread(str(path)) as raw:
        try:
            pattern = raw.raw_pattern
            pattern = pattern.tolist() if pattern is not None else None
        except rawpy.NotSupportedError:
            pattern = None
        result = {
            "path": str(path.resolve()), "sha256": sha256(path),
            "libraw_version": list(rawpy.libraw_version), "rawpy_version": rawpy.__version__,
            "sizes": raw.sizes._asdict(), "raw_type": raw.raw_type.name,
            "raw_shape": list(raw.raw_image.shape), "cfa_pattern": pattern,
            "black_level_per_channel": raw.black_level_per_channel,
            "white_level": raw.white_level, "camera_whitebalance": raw.camera_whitebalance,
            "rgb_xyz_matrix": raw.rgb_xyz_matrix.tolist(),
            "exif": exif(path), "exact_fuji_render": False,
        }
    result["seconds"] = round(time.monotonic() - started, 3)
    return result


def prepare(path: Path, output: Path, max_edge: int = 1500) -> dict:
    """Persist neutral linear input + JPEG reference separately with provenance."""
    require_local(path)
    if max_edge < 64 or max_edge > 6000:
        raise ValueError("max_edge must be between 64 and 6000.")
    info = probe(path)
    output.mkdir(parents=True, exist_ok=False)
    with rawpy.imread(str(path)) as raw:
        data = raw.postprocess(use_camera_wb=True, use_auto_wb=False, no_auto_bright=True,
                               output_bps=16, gamma=(1, 1), output_color=rawpy.ColorSpace.sRGB,
                               half_size=True)
        try:
            thumb = raw.extract_thumb()
            if thumb.format == rawpy.ThumbFormat.JPEG:
                (output / "embedded-reference.jpg").write_bytes(thumb.data)
                info["reference"] = "embedded-reference.jpg"
            else:
                Image.fromarray(thumb.data).save(output / "embedded-reference.png")
                info["reference"] = "embedded-reference.png"
        except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError):
            info["reference"] = None
    h, w = data.shape[:2]
    factor = min(1, max_edge / max(h, w))
    size = (round(w * factor), round(h * factor))
    linear = np.stack([np.asarray(Image.fromarray(data[:, :, c].astype(np.float32)).resize(size, Image.Resampling.LANCZOS)) for c in range(3)], axis=-1) / 65535
    linear = np.maximum(linear, 0).astype(np.float32)
    np.save(output / "neutral-linear-srgb.npy", linear, allow_pickle=False)
    display = np.where(linear <= 0.0031308, linear * 12.92, 1.055 * np.power(linear, 1 / 2.4) - 0.055)
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    Image.fromarray(np.round(np.clip(display, 0, 1) * 255).astype(np.uint8)).save(output / "neutral-preview.jpg", quality=95, icc_profile=icc)
    info["prepared"] = {"shape": list(linear.shape), "space": "linear sRGB", "dtype": "float32", "decoder": "LibRaw", "camera_pipeline": False, "candidate_fuji_input": False, "camera_wb": True, "auto_bright": False, "half_size_requested": True}
    info["reference_warning"] = "Embedded preview is the existing rendering of this file. It is not a newly executed recipe, a full-resolution reference, or proof of exactness. Orientation/crop may differ."
    (output / "manifest.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    return info
