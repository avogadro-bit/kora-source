"""Compare reduced-source reuse against the previous calculation, same pixels.

Run with an already-local RAW. No source file or application preference is edited.
The first decode is measured separately; each timed recipe uses a fresh JPEG.
"""
from io import BytesIO
from pathlib import Path
import argparse
import hashlib
import json
import platform
import statistics
import sys
import tempfile
import time

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kora import __version__
from kora.gui import Library, RenderRequest
from kora.raw import require_local
from kora.studio import StudioRecipe


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw',type=Path)
    parser.add_argument('--film',default='kodachrome64')
    parser.add_argument('--edge',type=int,default=1800)
    parser.add_argument('--runs',type=int,default=6)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    if not 2<=args.runs<=20:parser.error('--runs must be between 2 and 20')
    path=args.raw.resolve();require_local(path)
    before=hashlib.file_digest(path.open('rb'),'sha256').hexdigest()
    times={'uncached':[],'cached':[]};equal=[]
    with tempfile.TemporaryDirectory(prefix='kora-benchmark-') as temporary:
        library=Library([path.parent],Path(temporary))
        identifier=library.add(path)['id']
        started=time.perf_counter();linear=library.full_linear(identifier)
        decode_seconds=time.perf_counter()-started
        budget=library.display_source_budget
        request=RenderRequest(id=identifier,quality='display',edge=args.edge,
                              recipe=StudioRecipe(film=args.film))
        # Warm film-table loading and the reduced linear source, not JPEG caches.
        library.display_preview(request)
        for index in range(args.runs):
            recipe=StudioRecipe(film=args.film,exposure=(index-(args.runs-1)/2)/10)
            request=request.model_copy(update={'recipe':recipe})
            outputs={}
            modes=('uncached','cached') if index%2==0 else ('cached','uncached')
            for mode in modes:
                library.display_cache.clear()
                saved=library.display_source_cache
                if mode=='uncached':
                    library.display_source_cache=type(saved)();library.display_source_budget=0
                started=time.perf_counter();data,_=library.display_preview(request)
                times[mode].append(time.perf_counter()-started)
                if mode=='uncached':
                    library.display_source_cache=saved;library.display_source_budget=budget
                outputs[mode]=np.asarray(Image.open(BytesIO(data)))
            equal.append(bool(np.array_equal(outputs['uncached'],outputs['cached'])))
        shape=list(linear.shape)
    after=hashlib.file_digest(path.open('rb'),'sha256').hexdigest()
    report={'app_version':__version__,'system':platform.system(),'system_release':platform.release(),
            'architecture':platform.machine(),'python':platform.python_version(),'raw':path.name,
            'source_unchanged':before==after,'source_sha256':before,'shape':shape,'film':args.film,
            'display_edge':args.edge,'runs':args.runs,'decode_seconds':decode_seconds,
            'seconds':times,'pixels_equal':equal,'medians':{key:statistics.median(value) for key,value in times.items()},
            'scope':'Warm RAW and film tables, alternating cache on/off; server computation, not total UI click latency.'}
    report['speedup']=report['medians']['uncached']/report['medians']['cached']
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
    if not before==after or not all(equal):raise SystemExit('Pixel invariance failed.')


if __name__=='__main__':main()
