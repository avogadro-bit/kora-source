"""Local photographic studio with an independent RAW renderer."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager, nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import errno
import os
from pathlib import Path
import secrets
import socket
import sys
import hashlib
import tempfile
import threading
import time
import webbrowser
import zipfile
from typing import Literal
from urllib.parse import urlparse, parse_qs

from PIL import Image, ImageOps
import numpy as np
import rawpy

from .input_profiles import RAW_EXTENSIONS
from . import __version__
from .activity import user_activity
from .platform_support import physical_memory_bytes, drive_roots
from .diagnostics import record_error, install_hooks, register_secret, context_values
from .engine import status
from .lut_install import install_archive
from .official_luts import FILMS as OFFICIAL_FILMS, lut_worker_count
from .raw import local_file, exif
from .studio import StudioRecipe as Recipe, studio_status, decode, render, encode, shooting_settings, source_details
from pydantic import BaseModel, ConfigDict, Field, StrictBool


class RenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    recipe: Recipe
    neutral: StrictBool = False
    quality: Literal['interactive','full'] = 'full'


class TileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    recipe: Recipe
    neutral: StrictBool = False
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    size: int = Field(default=512, ge=128, le=1024)
    level: Literal[1,2,4,8] = 1
    view_id: str = Field(default='', max_length=64)
    generation: int = Field(default=0, ge=0)


class BatchExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[RenderRequest] = Field(min_length=2, max_length=100)


class PrefetchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64)

STATIC = Path(__file__).with_name("static")
# 100 MP 3FR originals can exceed 200 MiB. Imports are streamed to disk.
MAX_UPLOAD = 512*1024*1024
MAX_LUT_ARCHIVE = 160*1024*1024
MAX_BATCH_REQUEST = 512*1024
MAX_RECIPE_SIZE = 64*1024


def unsupported_raw_message(metadata):
    compression=str(metadata.get('NEFCompression','')).casefold()
    if str(metadata.get('Make','')).upper().startswith('NIKON') and 'high efficiency' in compression:
        return ('Nikon High Efficiency (HE/HE*) RAW is not supported by this version. '
                'Use a lossless-compressed or uncompressed NEF, or convert this file '
                'to DNG with a compatible RAW converter.')
    return ('This RAW camera or compression is not supported by the current decoder. '
            'Try a DNG conversion with a compatible RAW converter.')


def host_capacity(cpu_count=None, physical_memory=None):
    """Choose conservative image-level concurrency for the current computer.

    A full-resolution RAW can need several GiB while the float pipeline is
    active.  CPU capacity therefore sets an upper bound, while physical memory
    decides whether one, two, three, or four full images may run together.
    Thumbnail extraction is much lighter and can use more I/O concurrency.
    """
    cpu_count = max(1, int(cpu_count or os.cpu_count() or 1))
    if physical_memory is None:
        physical_memory = physical_memory_bytes()
    gib = max(1, int(physical_memory)//1024**3)
    memory_workers = max(1, (gib-4)//6)
    export_workers = min(4, max(1, cpu_count//3), memory_workers)
    thumbnail_workers = min(8, max(2, cpu_count//2))
    return {"cpu_count":cpu_count, "physical_memory":int(physical_memory),
            "export_workers":export_workers, "thumbnail_workers":thumbnail_workers,
            "render_workers":lut_worker_count(cpu_count),
            "full_resolution_prefetch":gib>=16}


def export_memory_gib(recipe):
    """Conservative peak-memory estimate for one full-resolution render."""
    estimate=6
    tone=any((recipe.highlights,recipe.whites,recipe.shadows,recipe.blacks)) or recipe.dynamic_range!=100 or recipe.dr_priority!='off'
    if tone:estimate+=2 if recipe.film in OFFICIAL_FILMS else 1
    if recipe.highlight_tone or recipe.shadow_tone:estimate+=1
    if recipe.clarity:estimate+=1
    if recipe.grain!='off':estimate+=1
    if recipe.smooth_skin!='off' or recipe.color_chrome!='off' or recipe.fx_blue!='off':estimate+=1
    if recipe.lens_distortion!='off' or recipe.lens_vignetting!='off':estimate+=2
    if recipe.color_space=='adobe_rgb':estimate+=1
    return estimate


def render_context(path):
    """Use the same source WB basis for previews, viewport tiles and exports."""
    from .camera_white_balance import source_render_context
    return source_render_context(path)


def output_geometry(shape, recipe):
    """Map the developed RAW into the recipe's final output coordinates."""
    h,w=shape[:2]
    cw,ch=int(w/recipe.digital_crop),int(h/recipe.digital_crop)
    if recipe.aspect!='original':
        rw,rh=map(int,recipe.aspect.split(':'));ratio=rw/rh
        if h>w:ratio=1/ratio
        if cw/ch>ratio:cw=round(ch*ratio)
        else:ch=round(cw/ratio)
    left,top=(w-cw)//2,(h-ch)//2
    factor={'L':1.,'M':.7071,'S':.5}[recipe.image_size]
    edge=round(max(cw,ch)*factor)
    if edge>=max(cw,ch):out_w,out_h=cw,ch
    else:out_w,out_h=max(1,round(cw*edge/max(cw,ch))),max(1,round(ch*edge/max(cw,ch)))
    return {'source':(left,top,cw,ch),'output':(out_w,out_h),'full':(w,h)}


def downsample_box(pixels, factor):
    """Memory-bounded area reduction for lower-resolution viewport levels."""
    if factor==1:return pixels
    h,w=pixels.shape[:2];out_h=(h+factor-1)//factor;out_w=(w+factor-1)//factor
    result=np.zeros((out_h,out_w,3),np.float32);counts=np.zeros((out_h,out_w),np.float32)
    for yy in range(factor):
        for xx in range(factor):
            sample=pixels[yy::factor,xx::factor]
            if not sample.size:continue
            sh,sw=sample.shape[:2];result[:sh,:sw]+=sample;counts[:sh,:sw]+=1
    result/=np.maximum(counts[:,:,None],1)
    return result


class Library:
    def __init__(self, roots, scratch, capacity=None):
        self.files = {}
        self.roots = [Path(p).expanduser().resolve() for p in roots] or [Path.home()]
        self.scratch = Path(scratch)
        self.previews = OrderedDict()
        self.thumbnails = OrderedDict()
        self.details = {}
        self.linear_cache = OrderedDict()
        self.corrected_cache = OrderedDict()
        self.tile_cache = OrderedDict()
        self.tile_generations = OrderedDict()
        self.optics_samples = OrderedDict()
        self.recipe_folder = None
        self.recipe_files = {}
        self.capacity = dict(capacity or host_capacity())
        self.lock = threading.RLock()
        # Separate cheap embedded-thumbnail I/O from memory-heavy RAW decode.
        # Distinct rawpy objects may work concurrently; the limits below keep
        # high-resolution float buffers inside a conservative memory budget.
        self.thumbnail_lock = threading.Semaphore(self.capacity["thumbnail_workers"])
        self.decoder_lock = threading.Semaphore(self.capacity["export_workers"])
        self.full_decode_lock = threading.Lock()
        self.full_render_lock = threading.Semaphore(self.capacity["export_workers"])
        self.tile_render_lock = threading.Semaphore(2)
        self.render_priority = threading.Condition()
        self.export_jobs = 0
        self.active_tile_renders = 0
        for root in self.roots:
            if not root.is_dir():
                raise ValueError(f"Folder not found: {root}")
            # Folder shortcuts only. Scan after explicit selection in the GUI.

    def folders(self, path=None):
        folder = Path(path).expanduser().resolve() if path else self.roots[0]
        if not folder.is_dir():
            raise ValueError("Folder not found.")
        # Authenticated local picker: paths are explicitly selected by the user.
        children = []
        raw_count = 0
        for p in sorted(folder.iterdir(), key=lambda p: p.name.casefold()):
            if not p.name.startswith('.') and p.is_dir():
                children.append({"name":p.name,"path":str(p.resolve())})
            elif p.is_file() and p.suffix.lower() in RAW_EXTENSIONS:
                raw_count += 1

        home = Path.home().resolve()
        shortcut_candidates = [
            ("Home", home),
            ("Desktop", home / "Desktop"),
            ("Pictures", home / "Pictures"),
            ("Documents", home / "Documents"),
            ("Downloads", home / "Downloads"),
            *[(str(drive), drive) for drive in drive_roots()],
            *[("Start Folder" if root == home else root.name or str(root), root) for root in self.roots],
        ]
        shortcuts, seen = [], set()
        for name, candidate in shortcut_candidates:
            candidate = candidate.resolve()
            if candidate.is_dir() and candidate not in seen:
                shortcuts.append({"name": name, "path": str(candidate)})
                seen.add(candidate)

        if folder == home or folder.is_relative_to(home):
            breadcrumbs = [{"name": "Home", "path": str(home)}]
            cursor = home
            if folder != home:
                for part in folder.relative_to(home).parts:
                    cursor /= part
                    breadcrumbs.append({"name": part, "path": str(cursor)})
        else:
            anchor = Path(folder.anchor)
            breadcrumbs = [{"name": folder.anchor or "/", "path": str(anchor)}]
            cursor = anchor
            for part in folder.parts[1:]:
                cursor /= part
                breadcrumbs.append({"name": part, "path": str(cursor)})

        return {
            "path": str(folder),
            "name": folder.name or str(folder),
            "parent": str(folder.parent) if folder.parent != folder else None,
            "folders": children,
            "shortcuts": shortcuts,
            "breadcrumbs": breadcrumbs,
            "raw_count": raw_count,
        }

    @staticmethod
    def _read_recipe(path):
        with path.open("rb") as stream:
            payload = stream.read(MAX_RECIPE_SIZE + 1)
        if len(payload) > MAX_RECIPE_SIZE:
            raise ValueError("The recipe exceeds 64 KB.")
        return Recipe.model_validate_json(payload)

    def select_recipe_folder(self, path):
        """Index valid JSON recipes in one explicitly selected local folder."""
        folder = Path(path).expanduser().resolve()
        if not folder.is_dir():
            raise ValueError("Recipe folder not found.")
        recipes, indexed, invalid = [], {}, 0
        for candidate in sorted(folder.iterdir(), key=lambda item: item.name.casefold()):
            if candidate.name.startswith('.') or candidate.suffix.lower() != '.json' or candidate.is_symlink():
                continue
            try:
                resolved = candidate.resolve(strict=True)
                if resolved.parent != folder or not resolved.is_file():
                    raise ValueError("Recipe is outside the selected folder.")
                parsed = self._read_recipe(resolved)
                stat = resolved.stat()
                identifier = hashlib.sha256(
                    f"{resolved}:{stat.st_size}:{stat.st_mtime_ns}".encode()
                ).hexdigest()[:24]
                item = {"id": identifier, "name": parsed.name, "filename": resolved.name,
                        "film": parsed.film}
                recipes.append(item)
                indexed[identifier] = resolved
            except Exception:
                invalid += 1
        with self.lock:
            self.recipe_folder = folder
            self.recipe_files = indexed
        return {"folder": str(folder), "name": folder.name or str(folder),
                "recipes": recipes, "invalid_count": invalid}

    def load_recipe(self, identifier):
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("Choose a recipe.")
        with self.lock:
            folder = self.recipe_folder
            path = self.recipe_files.get(identifier)
        if folder is None or path is None:
            raise ValueError("Recipe not found. Refresh the recipe folder.")
        try:
            resolved = path.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ValueError("Recipe file no longer exists. Refresh the recipe folder.") from exc
        if resolved.parent != folder or resolved.is_symlink() or not resolved.is_file():
            raise ValueError("Recipe is no longer inside the selected folder.")
        recipe = self._read_recipe(resolved)
        return {"recipe": recipe.model_dump(), "notes": recipe.unsupported(),
                "render_available": True, "filename": resolved.name}

    def select_folder(self, path, recursive=True):
        folder=Path(path).expanduser().resolve()
        if not folder.is_dir():raise ValueError("Folder not found.")
        iterator=folder.rglob('*') if recursive else folder.iterdir()
        selected=[]
        for p in sorted(iterator):
            if p.suffix.lower() in RAW_EXTENSIONS and p.is_file():
                selected.append(self.add(p,folder.name))
                if len(selected)>=5000:break
        return {"folder":str(folder),"files":selected,"limit_reached":len(selected)>=5000}

    def add(self, path, group="Imports"):
        path = path.resolve()
        st = path.stat()
        identifier = hashlib.sha256(f"{path}:{st.st_size}:{st.st_mtime_ns}".encode()).hexdigest()[:24]
        with self.lock:
            self.files[identifier] = {"id": identifier, "name": path.name, "path": str(path),
                                      "format": path.suffix[1:].upper(), "bytes": st.st_size,
                                      "local": local_file(path), "group": group}
            return self.files[identifier]

    def listing(self):
        with self.lock:
            return list(self.files.values())

    def performance(self):
        return dict(self.capacity)

    @contextmanager
    def export_slot(self):
        """Give exports priority over source-detail work already in flight."""
        with self.render_priority:
            self.export_jobs+=1
            while self.active_tile_renders:
                self.render_priority.wait()
        try:
            yield
        finally:
            with self.render_priority:
                self.export_jobs-=1
                self.render_priority.notify_all()

    @contextmanager
    def tile_slot(self):
        with self.render_priority:
            if self.export_jobs:
                raise ValueError('Source detail paused during export')
            self.active_tile_renders+=1
        try:
            yield
        finally:
            with self.render_priority:
                self.active_tile_renders-=1
                self.render_priority.notify_all()

    def check_export_priority(self):
        with self.render_priority:
            if self.export_jobs:
                raise ValueError('Source detail paused during export')

    def inspect(self, identifier):
        with self.decoder_lock:
            if identifier in self.details and (not self.details[identifier]["preview_available"] or identifier in self.previews):
                if identifier in self.previews:
                    self.previews.move_to_end(identifier)
                return self.details[identifier]
            with self.lock:
                item = self.files[identifier]
            # Recheck immediately before reading: iCloud residency can change
            # while the library remains open.
            if not local_file(Path(item["path"])):
                raise ValueError("This cloud file must be made available offline before it can be opened.")
            path = Path(item["path"])
            info = {**item, "exif": exif(path), "preview_available": False,
                    "preview_kind": "embedded", "recipe_applied": False, "exact_fuji_render": False}
            try:
                raw = rawpy.imread(str(path))
            except rawpy.LibRawFileUnsupportedError as exc:
                raise ValueError(unsupported_raw_message(info['exif'])) from exc
            with raw:
                info["sizes"] = raw.sizes._asdict()
                width,height=raw.sizes.width,raw.sizes.height
                if raw.sizes.flip in (5,6):width,height=height,width
                info["developed_size"]={"width":width,"height":height}
                try:
                    thumb = raw.extract_thumb()
                    picture = Image.open(BytesIO(thumb.data)) if thumb.format == rawpy.ThumbFormat.JPEG else Image.fromarray(thumb.data)
                    picture = ImageOps.exif_transpose(picture)
                    picture.thumbnail((1800, 1400), Image.Resampling.LANCZOS)
                    output = BytesIO()
                    picture.convert("RGB").save(output, format="JPEG", quality=90, icc_profile=picture.info.get("icc_profile"))
                    self.previews[identifier] = output.getvalue()
                    while len(self.previews) > 32:
                        self.previews.popitem(last=False)
                    info["preview_available"] = True
                    info["preview_size"] = list(picture.size)
                except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError):
                    info["preview_reason"] = "This file has no readable embedded preview."
            from .studio import source_details
            try:
                info["source_exposure"] = source_details(path)
            except rawpy.LibRawFileUnsupportedError as exc:
                # Some decoders can read metadata/thumbnail, then reject the
                # sensor compression only when development starts.
                raise ValueError(unsupported_raw_message(info['exif'])) from exc
            info["input_normalization"] = info["source_exposure"].get("normalization",{})
            info["shooting_settings"] = shooting_settings(info["exif"],restore_wb_shift=info.get("source_exposure",{}).get("white_balance",{}).get("shift_removed",False))
            from .optics import inspect_optics
            try:
                info["optics"] = inspect_optics(path)
            except (OSError, ValueError, RuntimeError) as exc:
                record_error('optics-inspection', exc, context={'photo_id': identifier})
                info["optics"] = {"distortion":False,"vignetting":False,"label":f"Lens profile unavailable: {exc}"}
            self.details[identifier] = info
            return info

    def thumbnail(self, identifier):
        """Return a small embedded RAW preview without running the render pipeline."""
        with self.thumbnail_lock:
            with self.lock:
                if identifier in self.thumbnails:
                    self.thumbnails.move_to_end(identifier)
                    return self.thumbnails[identifier]
                item = self.files[identifier]
            path = Path(item["path"])
            if not local_file(path):
                raise ValueError("This iCloud file must be downloaded before its thumbnail can be shown.")
            try:
                with self.lock:
                    preview = self.previews.get(identifier)
                if preview is not None:
                    picture = Image.open(BytesIO(preview))
                else:
                    with rawpy.imread(str(path)) as raw:
                        thumb = raw.extract_thumb()
                        picture = (Image.open(BytesIO(thumb.data)) if thumb.format == rawpy.ThumbFormat.JPEG
                                   else Image.fromarray(thumb.data))
                picture = ImageOps.exif_transpose(picture)
                picture.thumbnail((360, 240), Image.Resampling.LANCZOS)
                output = BytesIO()
                picture.convert("RGB").save(output, format="JPEG", quality=84,
                                            icc_profile=picture.info.get("icc_profile"))
            except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError):
                raise ValueError("This RAW file has no embedded thumbnail.") from None
            data = output.getvalue()
            with self.lock:
                self.thumbnails[identifier] = data
                while len(self.thumbnails) > 96:
                    self.thumbnails.popitem(last=False)
            return data


    def develop(self, request, export=False, timings=None):
        timings = timings if timings is not None else {}
        started=time.perf_counter()
        with self.lock:
            item = self.files[request.id]
        path = Path(item["path"])
        if not local_file(path):
            raise ValueError("The cloud file is not downloaded. Make it available offline first.")

        def finish(linear):
            stage=time.perf_counter()
            if request.recipe.lens_distortion != 'off' or request.recipe.lens_vignetting != 'off':
                from .optics import inspect_optics, apply_corrections
                linear=apply_corrections(linear,inspect_optics(path),
                                         request.recipe.lens_distortion,request.recipe.lens_vignetting)
            timings['optics']=time.perf_counter()-stage
            stage=time.perf_counter()
            context=render_context(path)
            timings['metadata']=time.perf_counter()-stage
            stage=time.perf_counter()
            pixels = render(linear, request.recipe, neutral=request.neutral,
                            context=context)
            timings['render']=time.perf_counter()-stage
            stage=time.perf_counter()
            result=encode(pixels, request.recipe, preview=not export)
            timings['encode']=time.perf_counter()-stage
            return result

        if not export and request.quality == 'interactive':
            # Serialize only LibRaw access, not the small render. An interactive
            # edit can therefore overtake an obsolete 60 MP refinement.
            with self.decoder_lock:
                linear = decode(path, preview=True)
            return finish(linear)

        # Full exports remain serialized to bound peak memory. Release the RAW
        # decoder as soon as its result is cached so reduced previews can render
        # concurrently with the expensive full-size effects pipeline.
        priority=self.export_slot() if export else nullcontext()
        with priority:
            with self.full_render_lock:
                timings['queue']=time.perf_counter()-started
                stage=time.perf_counter()
                linear=self.full_linear(request.id)
                timings['decode_or_prefetch_wait']=time.perf_counter()-stage
                return finish(linear)

    def full_linear(self, identifier, check_current=lambda:None):
        """Decode once; viewport tiles and export share the active RAW buffer."""
        with self.lock:
            item=self.files[identifier]
        path=Path(item['path'])
        if not local_file(path):
            raise ValueError("The cloud file is not downloaded. Make it available offline first.")
        # A counting decoder semaphore does not coalesce simultaneous cache
        # misses from prefetch, tiles and export. One cache fill owns this lock.
        with self.full_decode_lock, self.decoder_lock:
            check_current()
            if identifier not in self.linear_cache:
                self.linear_cache[identifier]=decode(path,preview=False)
                while len(self.linear_cache)>1:self.linear_cache.popitem(last=False)
            self.linear_cache.move_to_end(identifier)
            return self.linear_cache[identifier]

    def prefetch(self,identifier):
        """Use idle time and capable Macs to prepare the next full export."""
        if not self.capacity.get('full_resolution_prefetch',False):return False
        self.check_export_priority()
        self.full_linear(identifier,self.check_export_priority)
        return True

    def render_tile(self, request):
        """Render one source-resolution viewport tile, never a giant browser JPEG."""
        with self.lock:
            if request.view_id:
                self.tile_generations[request.view_id]=max(request.generation,self.tile_generations.get(request.view_id,0))
                self.tile_generations.move_to_end(request.view_id)
                while len(self.tile_generations)>128:self.tile_generations.popitem(last=False)
        def check_current():
            with self.lock:
                if request.view_id and request.generation<self.tile_generations.get(request.view_id,0):
                    raise ValueError('Superseded viewport')
            self.check_export_priority()
        check_current()
        recipe_key=hashlib.sha256(request.recipe.model_dump_json().encode()).hexdigest()[:20]
        cache_key=(request.id,recipe_key,request.neutral,request.x,request.y,request.size,request.level)
        with self.lock:
            if cache_key in self.tile_cache:
                self.tile_cache.move_to_end(cache_key)
                return self.tile_cache[cache_key]
            item=self.files[request.id]
        path=Path(item['path']);linear=self.full_linear(request.id,check_current)
        check_current();regional_profile=None
        optics_key=(request.id,request.recipe.lens_distortion,request.recipe.lens_vignetting)
        if request.recipe.lens_distortion!='off' or request.recipe.lens_vignetting!='off':
            from .optics import inspect_optics, apply_corrections, dng_corrected_region
            profile=inspect_optics(path)
            if profile.get('source')=='dng-warp' and request.recipe.lens_distortion=='auto':
                regional_profile=profile
        if (request.recipe.lens_distortion!='off' or request.recipe.lens_vignetting!='off') and regional_profile is None:
            with self.full_render_lock:
                check_current()
                with self.lock:corrected=self.corrected_cache.get(optics_key)
                if corrected is None:
                    from .optics import inspect_optics, apply_corrections
                    corrected=apply_corrections(linear,inspect_optics(path),
                        request.recipe.lens_distortion,request.recipe.lens_vignetting)
                    with self.lock:
                        self.corrected_cache[optics_key]=corrected
                        while len(self.corrected_cache)>1:self.corrected_cache.popitem(last=False)
            linear=corrected
        geometry=output_geometry(linear.shape,request.recipe)
        left,top,crop_w,crop_h=geometry['source'];out_w,out_h=geometry['output']
        if request.x>=out_w or request.y>=out_h:raise ValueError('Tile lies outside the developed image.')
        span=request.size*request.level
        tile_w=min(span,out_w-request.x);tile_h=min(span,out_h-request.y)
        sx0=left+(request.x*crop_w)//out_w
        sy0=top+(request.y*crop_h)//out_h
        sx1=left+((request.x+tile_w)*crop_w+out_w-1)//out_w
        sy1=top+((request.y+tile_h)*crop_h+out_h-1)//out_h
        halo=256;level=request.level
        rx0=max(0,((sx0-halo)//level)*level);ry0=max(0,((sy0-halo)//level)*level)
        rx1=min(linear.shape[1],((sx1+halo+level-1)//level)*level)
        ry1=min(linear.shape[0],((sy1+halo+level-1)//level)*level)
        sample_step=max(1,max(linear.shape[:2])//640)
        check_current()
        sample=linear[::sample_step,::sample_step]
        if regional_profile is not None:
            with self.lock:sample=self.optics_samples.get(optics_key)
            if sample is None:
                sample=dng_corrected_region(linear,regional_profile,(0,0,linear.shape[1],linear.shape[0]),sample_step)
                with self.lock:
                    self.optics_samples[optics_key]=sample
                    while len(self.optics_samples)>2:self.optics_samples.popitem(last=False)
            region=dng_corrected_region(linear,regional_profile,(rx0,ry0,rx1,ry1))
        else:region=linear[ry0:ry1,rx0:rx1]
        context={'sample':sample,
                 'full_shape':((linear.shape[0]+level-1)//level,
                               (linear.shape[1]+level-1)//level,3),
                 **render_context(path)}
        region=downsample_box(region,level)
        with self.tile_render_lock:
            with self.tile_slot():
                check_current()
                pixels=render(region,request.recipe,neutral=request.neutral,output_transform=False,context=context,
                              origin=(ry0//level,rx0//level))
        crop_x0=(sx0-rx0)//level;crop_y0=(sy0-ry0)//level
        crop_x1=(sx1-rx0+level-1)//level;crop_y1=(sy1-ry0+level-1)//level
        pixels=pixels[crop_y0:crop_y1,crop_x0:crop_x1]
        target_w=max(1,(tile_w+request.level-1)//request.level)
        target_h=max(1,(tile_h+request.level-1)//request.level)
        if pixels.shape[1]!=target_w or pixels.shape[0]!=target_h:
            pixels=np.stack([np.asarray(Image.fromarray(pixels[:,:,channel]).resize(
                (target_w,target_h),Image.Resampling.LANCZOS)) for channel in range(3)],axis=-1)
        data,mime=encode(pixels,request.recipe,preview=True,detail=True)
        result=(data,mime)
        with self.lock:
            self.tile_cache[cache_key]=result
            while len(self.tile_cache)>96:self.tile_cache.popitem(last=False)
        return result

    def _develop_batch_item(self, request):
        """Develop one uncached batch item inside the shared memory budget."""
        # Batch items do not enter the one-photo cache: retaining several 60 MP
        # float buffers would erase the memory bound from the worker pool.
        with self.lock:
            path = Path(self.files[request.id]["path"])
        if not local_file(path):
            raise ValueError("The cloud file is not downloaded. Make it available offline first.")
        with self.export_slot():
            with self.full_render_lock:
                with self.lock:
                    linear=self.linear_cache.get(request.id)
                    if linear is not None:self.linear_cache.move_to_end(request.id)
                if linear is None:
                    with self.decoder_lock:
                        linear = decode(path, preview=False)
                if request.recipe.lens_distortion != 'off' or request.recipe.lens_vignetting != 'off':
                    from .optics import inspect_optics, apply_corrections
                    linear = apply_corrections(linear, inspect_optics(path),
                                               request.recipe.lens_distortion,
                                               request.recipe.lens_vignetting)
                return encode(render(linear, request.recipe, neutral=request.neutral,
                                     context=render_context(path)),
                              request.recipe, preview=False)

    def batch_export_workers(self,requests):
        """Keep heavy recipes below memory pressure while filling CPU cores."""
        if not requests:return 1
        memory_gib=max(1,self.capacity.get("physical_memory",8*1024**3)/1024**3)
        reserve=4 if memory_gib<=16 else 6
        per_job=max(export_memory_gib(request.recipe) for request in requests)
        memory_workers=max(1,int(max(per_job,memory_gib-reserve)//per_job))
        return min(self.capacity["export_workers"],len(requests),memory_workers)

    def export_jpeg_archive(self, requests):
        """Render independent photos concurrently, then stream them into a ZIP."""
        identifiers = [request.id for request in requests]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Each photo may appear only once in a batch export.")
        if any(request.recipe.file_type != "jpeg" for request in requests):
            raise ValueError("Batch export supports JPEG output only.")
        with self.lock:
            missing = [identifier for identifier in identifiers if identifier not in self.files]
        if missing:
            raise ValueError("One or more selected photos are no longer in the library.")

        archive_path = self.scratch/f"kora-{secrets.token_hex(12)}.zip"
        used_names = set()
        jobs = []
        for index, request in enumerate(requests, 1):
            with self.lock:
                source_name = self.files[request.id]["name"]
            stem = "".join(character if character.isalnum() or character in "-_ ." else "_"
                           for character in Path(source_name).stem).strip(" .") or f"photo-{index}"
            candidate = f"{stem}-{request.recipe.film}.jpg"
            suffix = 2
            while candidate.casefold() in used_names:
                candidate = f"{stem}-{request.recipe.film}-{suffix}.jpg"
                suffix += 1
            used_names.add(candidate.casefold())
            jobs.append((candidate, request))

        try:
            with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_STORED) as archive:
                workers = self.batch_export_workers(requests)
                with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="raw-export") as pool:
                    futures = {pool.submit(self._develop_batch_item, request): candidate
                               for candidate, request in jobs}
                    for future in as_completed(futures):
                        candidate = futures[future]
                        data, mime = future.result()
                        if mime != "image/jpeg":
                            raise ValueError("Batch export produced a non-JPEG image.")
                        archive.writestr(candidate, data)
        except Exception:
            archive_path.unlink(missing_ok=True)
            raise
        return archive_path


class Handler(BaseHTTPRequestHandler):
    def log_error(self, format, *args):
        record_error('http-protocol', message=format % args)

    def diagnostic_context(self):
        context = {'source': self.command, 'request_id': self.headers.get('X-Film-Request-ID', '')[:64]}
        request = getattr(self, 'diagnostic_request', None)
        if request is not None:
            for name in ('x', 'y', 'size', 'level', 'generation'):
                if hasattr(request, name): context[name] = getattr(request, name)
            if hasattr(request, 'id'): context['photo_id'] = request.id
            if hasattr(request, 'recipe'):
                context.update(film=request.recipe.film, grain=request.recipe.grain,
                               grain_size=request.recipe.grain_size,
                               recipe_hash=hashlib.sha256(request.recipe.model_dump_json().encode()).hexdigest()[:16])
        else:
            route = urlparse(self.path).path
            if route.startswith(('/api/photo/', '/api/thumbnail/', '/api/preview/')):
                context['photo_id'] = route.rsplit('/', 1)[-1]
        return context

    def failure(self, exc, code=422):
        event = record_error(urlparse(self.path).path.strip('/').replace('/', '.'), exc,
                             context={**self.diagnostic_context(), 'status': code})
        self.send(code, {'error': str(exc), 'error_id': event, 'diagnostic_recorded': True})

    def log_message(self, *_):
        pass  # No file paths, session tokens or recipe contents in HTTP logs.

    def send(self, code, data, content_type="application/json; charset=utf-8"):
        if code >= 400 and isinstance(data, dict) and not data.get('diagnostic_recorded'):
            event = record_error(urlparse(self.path).path.strip('/').replace('/', '.'),
                                 message=data.get('error', 'HTTP error'),
                                 context={**self.diagnostic_context(), 'status': code})
            data = {**data, 'error_id': event}
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if getattr(self,'export_timings',None):
            self.send_header('Server-Timing',', '.join(
                f'{key};dur={value*1000:.2f}' for key,value in self.export_timings.items()))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass  # The browser may abort an obsolete image request.

    def send_file(self, path, content_type, download_name):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        try:
            with path.open("rb") as stream:
                while chunk := stream.read(1024*1024):
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def authorized(self):
        host = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host") != host or self.headers.get("Origin", f"http://{host}") != f"http://{host}":
            self.send(403, {"error": "Unauthorized origin"})
            return False
        if not secrets.compare_digest(self.headers.get("X-Fuji-Session", ""), self.server.session_token):
            self.send(403, {"error": "Session expired. Reopen the link displayed at launch."})
            return False
        return True

    def do_GET(self):
        route = urlparse(self.path).path
        static = {"/": ("index.html", "text/html; charset=utf-8"),
                  "/viewer.js": ("viewer.js", "application/javascript; charset=utf-8"),
                  "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                  "/diagnostics.js": ("diagnostics.js", "text/javascript; charset=utf-8"),
                  "/kora.css": ("kora.css", "text/css; charset=utf-8"),
                  "/style.css": ("style.css", "text/css; charset=utf-8")}
        if route in static:
            filename, mime = static[route]
            return self.send(200, (STATIC/filename).read_bytes(), mime)
        if not self.authorized():
            return
        try:
            if route == "/api/folders":
                return self.send(200,self.server.library.folders(parse_qs(urlparse(self.path).query).get("path",[None])[0]))
            if route == "/api/health":
                return self.send(200, {"ready": True})
            if route == "/api/library":
                return self.send(200, {"version":__version__, "files": self.server.library.listing(), "engine": studio_status(),
                                      "native_engine": status(), "recipe": Recipe().model_dump(),
                                      "native_window": callable(getattr(self.server, "toggle_fullscreen", None)),
                                      "performance": self.server.library.performance()})
            if route.startswith("/api/photo/"):
                return self.send(200, self.server.library.inspect(route.split("/")[-1]))
            if route.startswith("/api/preview/"):
                identifier = route.split("/")[-1]
                self.server.library.inspect(identifier)
                return self.send(200, self.server.library.previews[identifier], "image/jpeg")
            if route.startswith("/api/thumbnail/"):
                identifier = route.split("/")[-1]
                return self.send(200, self.server.library.thumbnail(identifier), "image/jpeg")
            self.send(404, {"error": "Resource not found"})
        except KeyError as exc:
            self.failure(exc, 404)
        except Exception as exc:
            self.failure(exc)

    def do_POST(self):
        route=urlparse(self.path).path
        with user_activity() if route in {'/api/export','/api/export-batch','/api/render','/api/tile','/api/prefetch'} else nullcontext():
            self.handle_post()

    def handle_post(self):
        if not self.authorized():
            return
        route = urlparse(self.path)
        try:
            self.connection.settimeout(60)
            length = int(self.headers.get("Content-Length", "0"))
            limit = (MAX_UPLOAD if route.path == "/api/import" else
                     MAX_LUT_ARCHIVE if route.path == "/api/luts/install" else
                     MAX_BATCH_REQUEST if route.path == "/api/export-batch" else 65536)
            if not 0 < length <= limit:
                maximum = (f"{MAX_UPLOAD//1024//1024} MiB" if route.path == "/api/import" else
                           "160 MB" if route.path == "/api/luts/install" else
                           "512 KB" if route.path == "/api/export-batch" else "64 KB")
                return self.send(413, {"error": f"File too large or empty request (maximum: {maximum})."})
            if route.path == "/api/import":
                name = Path(parse_qs(route.query).get("name", [""])[0]).name
                if Path(name).suffix.lower() not in RAW_EXTENSIONS:
                    return self.send(415, {"error": "Choose a compatible RAW: RAF, DNG, CR2/CR3, NEF, ARW, RW2, ORF…"})
                folder = self.server.library.scratch/secrets.token_hex(12)
                folder.mkdir()
                path = folder/name
                self.connection.settimeout(60)
                with path.open("xb") as stream:
                    remaining = length
                    while remaining:
                        chunk = self.rfile.read(min(1024*1024, remaining))
                        if not chunk:
                            raise ValueError("Import interrupted")
                        stream.write(chunk)
                        remaining -= len(chunk)
                return self.send(201, self.server.library.add(path))
            if route.path == "/api/luts/install":
                if self.headers.get('Content-Type', '').split(';')[0] == 'application/json':
                    if length > 65536:
                        raise ValueError('LUT path request is too large')
                    value = json.loads(self.rfile.read(length))
                    if not isinstance(value, dict) or not isinstance(value.get('path'), str) or not value['path'].strip():
                        raise ValueError('Choose a LUT ZIP or extracted folder')
                    install_archive(Path(value['path']).expanduser())
                    engine = studio_status()
                    return self.send(201, {"installed": not engine["missing_luts"], "engine": engine})
                name = Path(parse_qs(route.query).get("name", [""])[0]).name
                if Path(name).suffix.lower() != ".zip":
                    return self.send(415, {"error": "Choose the GFX ETERNA 55 ZIP archive downloaded from Fujifilm."})
                path = self.server.library.scratch/f"luts-{secrets.token_hex(12)}.zip"
                try:
                    with path.open("xb") as stream:
                        remaining = length
                        while remaining:
                            chunk = self.rfile.read(min(1024*1024, remaining))
                            if not chunk:
                                raise ValueError("LUT archive upload interrupted")
                            stream.write(chunk)
                            remaining -= len(chunk)
                    install_archive(path)
                finally:
                    path.unlink(missing_ok=True)
                engine = studio_status()
                return self.send(201, {"installed": not engine["missing_luts"], "engine": engine})
            body = self.rfile.read(length)
            if route.path == '/api/diagnostics':
                if length > 16384:
                    return self.send(413, {'error': 'Diagnostic event too large'})
                value = json.loads(body)
                if not isinstance(value, dict) or not isinstance(value.get('message'), str):
                    raise ValueError('Invalid diagnostic event')
                context = value.get('context', {})
                if not isinstance(context, dict): raise ValueError('Invalid diagnostic context')
                # The authenticated client is still bounded in case of an error loop.
                now = time.monotonic()
                with self.server.library.lock:
                    recent = [t for t in getattr(self.server, 'diagnostic_events', []) if now-t < 60]
                    allowed = len(recent) < 120
                    if allowed: recent.append(now)
                    self.server.diagnostic_events = recent
                if not allowed:
                    return self.send(429, {'error': 'Diagnostic rate limit', 'diagnostic_recorded': True})
                event = record_error('client.' + str(value.get('operation', 'error'))[:80],
                                     message=value['message'][:4000],
                                     stack=str(value.get('stack', ''))[:8000],
                                     context=context_values(context))
                return self.send(200 if event else 503, {'id': event, 'recorded': bool(event)})
            if route.path == "/api/window/fullscreen":
                toggle = getattr(self.server, "toggle_fullscreen", None)
                if not callable(toggle):
                    return self.send(409, {"error": "No native window in browser mode."})
                toggle()
                return self.send(200, {"ok": True})
            if route.path == "/api/folder":
                value=json.loads(body)
                if not isinstance(value,dict) or not isinstance(value.get("path"),str) or not value["path"].strip() or not isinstance(value.get("recursive",True),bool):
                    raise ValueError("Invalid folder selection.")
                return self.send(200,self.server.library.select_folder(value["path"],value.get("recursive",True)))
            if route.path == "/api/recipes/folder":
                value=json.loads(body)
                if not isinstance(value,dict) or not isinstance(value.get("path"),str) or not value["path"].strip():
                    raise ValueError("Invalid recipe folder selection.")
                return self.send(200,self.server.library.select_recipe_folder(value["path"]))
            if route.path == "/api/recipes/load":
                value=json.loads(body)
                if not isinstance(value,dict) or not isinstance(value.get("id"),str):
                    raise ValueError("Invalid recipe selection.")
                return self.send(200,self.server.library.load_recipe(value["id"]))
            if route.path == "/api/recipe":
                recipe = Recipe.model_validate_json(body)
                return self.send(200, {"recipe": recipe.model_dump(), "notes": recipe.unsupported(), "render_available": True})
            if route.path == "/api/prefetch":
                request=PrefetchRequest.model_validate_json(body)
                self.diagnostic_request = request
                return self.send(200,{"ready":self.server.library.prefetch(request.id)})
            if route.path == "/api/tile":
                request = TileRequest.model_validate_json(body)
                self.diagnostic_request = request
                data,mime = self.server.library.render_tile(request)
                return self.send(200,data,mime)
            if route.path in {"/api/render", "/api/export"}:
                request = RenderRequest.model_validate_json(body)
                self.diagnostic_request = request
                if route.path == "/api/export":
                    self.connection.settimeout(3600)
                    started=time.perf_counter();timings={}
                    data,mime=self.server.library.develop(request,export=True,timings=timings)
                    timings['server']=time.perf_counter()-started
                    self.export_timings=timings
                    self.send(200,data,mime)
                    timings['response_write']=time.perf_counter()-started-timings['server']
                    self.record_export(timings,len(data))
                    return
                data, mime = self.server.library.develop(request, export=route.path == "/api/export")
                return self.send(200, data, mime)
            if route.path == "/api/export-batch":
                request = BatchExportRequest.model_validate_json(body)
                self.connection.settimeout(3600)
                archive = self.server.library.export_jpeg_archive(request.items)
                try:
                    return self.send_file(archive, "application/zip", "kora-export.zip")
                finally:
                    archive.unlink(missing_ok=True)
            self.send(404, {"error": "Command not found"})
        except Exception as exc:
            self.failure(exc)

    def record_export(self,timings,size):
        # Local diagnostics contain no photo paths, image pixels or session keys.
        from .desktop import log_path
        try:
            path=log_path().with_name('exports.jsonl');path.parent.mkdir(parents=True,exist_ok=True)
            if path.exists() and path.stat().st_size>1024*1024:
                path.replace(path.with_suffix('.previous.jsonl'))
            with path.open('a',encoding='utf-8') as stream:
                stream.write(json.dumps({'version':__version__,'time':time.time(),
                    'seconds':timings,'bytes':size})+'\n')
        except OSError:
            pass


class StudioHTTPServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR can steal an active listener instead of failing.
    allow_reuse_address = sys.platform != 'win32'

    def server_bind(self):
        if sys.platform == 'win32':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def handle_error(self, request, client_address):
        record_error('http-worker', sys.exc_info()[1])


def bind_studio_server(port):
    try:
        return StudioHTTPServer(("127.0.0.1", port), Handler)
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE and not (sys.platform == 'win32' and getattr(exc, 'winerror', None) in (10013, 10048)):
            raise
        # Let the OS select and reserve a free port atomically.
        return StudioHTTPServer(("127.0.0.1", 0), Handler)


def serve(roots, port=8765, open_browser=False, on_ready=None):
    install_hooks()
    if not 1024 <= port <= 65535:
        raise ValueError("Port must be between 1024 and 65535")
    with tempfile.TemporaryDirectory(prefix="kora-") as scratch:
        server = bind_studio_server(port)
        server.daemon_threads = True
        server.session_token = secrets.token_urlsafe(32)
        register_secret(server.session_token)
        server.library = Library(roots, scratch)
        session_url = f"http://127.0.0.1:{server.server_port}/#session={server.session_token}"
        if server.server_port != port:
            print(f"Port {port} is already in use. Opening on available port {server.server_port}.", flush=True)
        print(f"KŌRA : {session_url}", flush=True)
        print("Local service. Press Ctrl+C to quit. Temporary imports are removed at shutdown.", flush=True)
        if open_browser:
            # Defer browser launch until serve_forever has started accepting requests.
            launcher = threading.Timer(0.2, webbrowser.open, args=(session_url,), kwargs={"new": 2})
            launcher.daemon = True
            launcher.start()
        try:
            if on_ready is not None:
                on_ready(server, session_url)
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
