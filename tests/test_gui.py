from kora.official_luts import missing_luts
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
import zipfile

from kora.gui import Handler, Library, STATIC, TileRequest, bind_studio_server, host_capacity, output_geometry
from kora.studio import StudioRecipe


class StaticGuiTests(unittest.TestCase):
    def test_unavailable_lmo_and_hdr_controls_are_not_shown(self):
        script=(STATIC/'app.js').read_text(encoding='utf-8')
        self.assertNotIn('Lens Modulation Optimizer',script)
        self.assertNotIn('Multi-exposure HDR',script)
        self.assertNotIn('"lens_optimizer"',script)
        self.assertNotIn('"hdr"',script)

    def test_host_capacity_scales_with_cpu_and_memory_without_unbounded_raw_workers(self):
        self.assertEqual(host_capacity(4,8*1024**3)['export_workers'],1)
        self.assertEqual(host_capacity(8,16*1024**3)['export_workers'],2)
        capacity=host_capacity(14,36*1024**3)
        self.assertEqual((capacity['export_workers'],capacity['thumbnail_workers']),(4,7))
        self.assertEqual(capacity['render_workers'],10)
        self.assertFalse(host_capacity(8,8*1024**3)['full_resolution_prefetch'])
        self.assertTrue(capacity['full_resolution_prefetch'])

    def test_product_name_batch_selection_and_film_chrome_are_visible(self):
        script=(STATIC/'app.js').read_text(encoding='utf-8')
        page=(STATIC/'index.html').read_text(encoding='utf-8')
        style=(STATIC/'style.css').read_text(encoding='utf-8')
        self.assertIn('<title>KŌRA</title>',page)
        self.assertIn('aria-label="KŌRA"',page)
        self.assertNotIn('One photograph. A thousand nuances.',page)
        self.assertIn('class="film-edge film-edge-top"',page)
        self.assertIn('const selectedIds = new Set(), recipesById = new Map();',script)
        self.assertIn('applyPatchToSelection',script)
        self.assertIn('/api/export-batch',script)
        self.assertIn('/api/thumbnail/',script)
        self.assertIn('/api/prefetch',script)
        self.assertIn('fullResolutionPrefetch=!!data.performance?.full_resolution_prefetch',script)
        self.assertIn('performance.now()',script)
        self.assertNotIn('x.Model?',script)
        self.assertIn('id="selection-clear"',page)
        self.assertIn('id="activity-bar"',page)
        for edge in ('data-resize="left"','data-resize="right"','data-resize="top"','data-resize="bottom"'):
            self.assertIn(edge,page)
        self.assertIn('beginActivity();',script)
        self.assertIn('localStorage.setItem("film-view-layout"',script)
        self.assertIn('.activity-bar',style)
        self.assertIn('@keyframes activity-spin',style)
        self.assertNotIn('activity-sweep',style)
        self.assertIn('prefers-reduced-motion:reduce',style)
        self.assertIn('id="fullscreen"',page)
        self.assertIn('id="recipe-library-select"',page)
        self.assertIn('id="choose-recipe-folder"',page)
        self.assertNotIn('id="load-recipe"',page)
        self.assertNotIn('id="recipe-input"',page)
        self.assertIn('/api/recipes/folder',script)
        self.assertIn('/api/recipes/load',script)
        self.assertIn('localStorage.setItem("film-recipe-folder"',script)
        self.assertIn('/api/window/fullscreen',script)
        self.assertIn('document.documentElement.requestFullscreen()',script)
        self.assertIn('.panel-resizer',style)
        self.assertIn('strip-active-badge',style)
        self.assertIn('.strip-entry.batch-selected',style)

    def test_full_resolution_view_preserves_ratio_without_transforming_60mp_bitmap(self):
        script=(STATIC/'app.js').read_text(encoding='utf-8')
        page=(STATIC/'index.html').read_text(encoding='utf-8')
        self.assertIn('id="detail-layer"',page)
        self.assertIn('const geometry=outputGeometry(),displayWidth=geometry.width*viewScale,displayHeight=geometry.height*viewScale;',script)
        self.assertIn('photo.style.width=displayWidth+"px";photo.style.height=displayHeight+"px";',script)
        self.assertIn('/api/tile',script)
        self.assertIn('SOURCE-RESOLUTION DETAIL',script)
        self.assertIn('image.dataset.x=x;image.dataset.y=y;image.dataset.width=width;image.dataset.height=height',script)
        self.assertIn('layoutDetailTiles();',script)
        self.assertIn('if(delay<=0){refreshVisibleTiles();return;}',script)
        self.assertIn('KoraViewer.planTiles',script)
        self.assertIn('KoraViewer.DetailQueue',script)
        self.assertIn('await image.decode()',script)
        self.assertIn('src="/viewer.js"',page)
        self.assertNotIn('viewScale<1',script)
        self.assertNotIn('queueRender("full")',script)
        self.assertNotIn('scale(${viewScale})',script)

    def test_four_way_tone_controls_and_interactive_preview_are_wired(self):
        script=(STATIC/'app.js').read_text(encoding='utf-8')
        for control in ('Highlights","highlights"','Whites","whites"',
                        'Shadows","shadows"','Blacks","blacks"'):
            self.assertIn(control,script)
        self.assertIn('QUICK PREVIEW',script)
        self.assertIn('body:JSON.stringify({id,recipe:settings,quality:"interactive"})',script)
        self.assertIn('renderController?.abort()',script)


class GuiServerTests(unittest.TestCase):
    def test_export_reports_server_stages_and_records_completed_transfer(self):
        from unittest.mock import patch
        import numpy as np
        path=Path(self.scratch.name)/'timed.DNG';path.write_bytes(b'fixture')
        item=self.server.library.add(path)
        self.server.library.linear_cache[item['id']]=np.ones((12,18,3),np.float32)
        body=json.dumps({'id':item['id'],'recipe':{}})
        with patch('kora.gui.render_context',return_value={}), \
             patch('kora.gui.render',side_effect=lambda pixels,*args,**kwargs:pixels), \
             patch('kora.gui.encode',return_value=(b'jpeg','image/jpeg')), \
             patch.object(Handler,'record_export') as recorded:
            client=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
            client.request('POST','/api/export',body,{'X-Fuji-Session':self.server.session_token})
            response=client.getresponse()
            self.assertEqual(response.status,200)
            timing=response.getheader('Server-Timing')
            self.assertEqual(response.read(),b'jpeg');client.close()
            for stage in ('queue','decode_or_prefetch_wait','optics','metadata','render','encode','server'):
                self.assertIn(stage+';dur=',timing)
            # Wait for handler cleanup after receipt of the HTTP response.
            self.server.shutdown()
            recorded.assert_called_once()
            self.assertIn('response_write',recorded.call_args.args[0])

    def test_dng_tiles_correct_only_region_and_preserve_full_frame_result(self):
        from unittest.mock import patch
        import numpy as np
        from kora.optics import apply_corrections
        library=self.server.library
        path=Path(self.scratch.name)/'regional.dng';path.write_bytes(b'raw')
        item=library.add(path)
        pixels=np.random.default_rng(4).uniform(-.1,3,(900,1200,3)).astype(np.float32)
        library.linear_cache[item['id']]=pixels
        profile={'source':'dng-warp','orientation':1,'distortion':True,'vignetting':False,
                 'warp':{'coefficients':[1,-.1,0,0,0,0],'center':[.4,.55]}}
        recipe=StudioRecipe(lens_distortion='auto')
        request=TileRequest(id=item['id'],recipe=recipe,x=512,y=256,size=128,level=2)
        # This checks regional geometry, not the proprietary LUT contents.
        with patch('kora.optics.inspect_optics',return_value=profile), \
             patch('kora.studio.apply_official',side_effect=lambda pixels,*args:pixels):
            actual=library.render_tile(request)
        self.assertFalse(library.corrected_cache)
        library.tile_cache.clear()
        library.corrected_cache[(item['id'],'auto','off')]=apply_corrections(pixels,profile,'auto')
        # Force the generic full-frame path for a byte-for-byte output comparison.
        with patch('kora.optics.inspect_optics',return_value={**profile,'source':'test-full'}), \
             patch('kora.studio.apply_official',side_effect=lambda pixels,*args:pixels):
            expected=library.render_tile(request)
        # ICC profiles include their creation time; crossing a second must
        # not make an otherwise identical regional render fail this check.
        from PIL import Image
        from io import BytesIO
        self.assertEqual(actual[1],expected[1])
        np.testing.assert_array_equal(np.asarray(Image.open(BytesIO(actual[0]))),
                                      np.asarray(Image.open(BytesIO(expected[0]))))

    def test_superseded_tile_is_rejected_before_decode(self):
        from unittest.mock import patch
        library=self.server.library
        library.tile_generations['tab']=8
        request=TileRequest(id='unused',recipe=StudioRecipe(),x=0,y=0,view_id='tab',generation=7)
        with patch('kora.gui.decode') as decode:
            with self.assertRaisesRegex(ValueError,'Superseded viewport'):
                library.render_tile(request)
            decode.assert_not_called()

    def test_health_requires_active_session(self):
        self.assertEqual(self.request('/api/health'), (200, {'ready': True}))
        self.assertEqual(self.request('/api/health', headers={'X-Fuji-Session':'old-session'})[0], 403)

    def test_source_resolution_tile_uses_full_decode_context_and_cache(self):
        from unittest.mock import patch
        import numpy as np
        path=Path(self.scratch.name)/'tile.DNG';path.write_bytes(b'fixture')
        item=self.server.library.add(path)
        pixels=np.random.default_rng(4).uniform(0,.8,(360,540,3)).astype(np.float32)
        self.server.library.linear_cache[item['id']]=pixels
        request=TileRequest(id=item['id'],recipe=StudioRecipe(noise_reduction=-4),x=128,y=128,size=128)
        observed=[]
        def renderer(region,recipe,**kwargs):
            observed.append((region.shape,kwargs))
            return region
        with patch('kora.gui.render',side_effect=renderer), \
             patch('kora.gui.encode',side_effect=lambda tile,*args,**kwargs:(tile.shape,'image/jpeg')) as encoder:
            shape,mime=self.server.library.render_tile(request)
            again=self.server.library.render_tile(request)
        self.assertEqual((shape,mime),((128,128,3),'image/jpeg'))
        self.assertEqual(again,(shape,mime))
        self.assertEqual(len(observed),1)
        self.assertFalse(observed[0][1]['output_transform'])
        self.assertEqual(observed[0][1]['context']['full_shape'],pixels.shape)
        self.assertEqual(encoder.call_count,1)
        self.assertTrue(encoder.call_args.kwargs['detail'])

        # Comparing without film must have an independent tile cache, while
        # retaining the exact same crop/zoom geometry as the recipe.
        neutral=request.model_copy(update={'neutral':True})
        with patch('kora.gui.render',side_effect=renderer), \
             patch('kora.gui.encode',side_effect=lambda tile,*args,**kwargs:(tile.shape,'image/jpeg')):
            shape,mime=self.server.library.render_tile(neutral)
        self.assertEqual(shape,(128,128,3))
        self.assertEqual(len(observed),2)
        self.assertTrue(observed[-1][1]['neutral'])

        level_two=TileRequest(id=item['id'],recipe=StudioRecipe(noise_reduction=-4),x=128,y=128,size=128,level=2)
        with patch('kora.gui.render',side_effect=lambda region,*args,**kwargs:region), \
             patch('kora.gui.encode',side_effect=lambda tile,*args,**kwargs:(tile.shape,'image/jpeg')):
            shape,mime=self.server.library.render_tile(level_two)
        self.assertEqual((shape,mime),((116,128,3),'image/jpeg'))

    def test_output_geometry_matches_crop_and_size_controls(self):
        geometry=output_geometry((4000,6000,3),StudioRecipe(digital_crop=2,aspect='1:1',image_size='M'))
        self.assertEqual(geometry['source'],(2000,1000,2000,2000))
        self.assertEqual(geometry['output'],(1414,1414))

    def test_carousel_thumbnail_endpoint_uses_small_preview_cache(self):
        path=Path(self.scratch.name)/'thumbnail.DNG';path.write_bytes(b'fixture')
        item=self.server.library.add(path)
        self.server.library.thumbnails[item['id']]=b'small-jpeg-preview'
        code,data=self.request('/api/thumbnail/'+item['id'])
        self.assertEqual((code,data),(200,b'small-jpeg-preview'))
        self.assertEqual(self.request('/api/thumbnail/missing')[0],404)

    def test_batch_export_uses_each_photo_recipe_and_returns_zip(self):
        from unittest.mock import patch
        first=Path(self.scratch.name)/'first.DNG';first.write_bytes(b'first')
        second=Path(self.scratch.name)/'second.RAF';second.write_bytes(b'second')
        a=self.server.library.add(first);b=self.server.library.add(second)
        observed=[]

        def develop(request):
            observed.append((request.id,request.recipe.exposure))
            return f'{request.id}:{request.recipe.exposure}'.encode(),'image/jpeg'

        body=json.dumps({'items':[
            {'id':a['id'],'recipe':{'exposure':-1,'file_type':'jpeg'}},
            {'id':b['id'],'recipe':{'exposure':1,'file_type':'jpeg'}},
        ]})
        with patch.object(Library,'_develop_batch_item',side_effect=develop):
            code,data=self.request('/api/export-batch','POST',body)
        self.assertEqual(code,200)
        with zipfile.ZipFile(__import__('io').BytesIO(data)) as archive:
            self.assertEqual(len(archive.namelist()),2)
            payloads=[archive.read(name) for name in archive.namelist()]
        self.assertCountEqual(observed,[(a['id'],-1.0),(b['id'],1.0)])
        self.assertNotEqual(payloads[0],payloads[1])
        # Receiving the body can precede the handler's finally/unlink on Windows.
        self.server.shutdown()
        self.server.server_close()
        self.assertFalse(list(Path(self.scratch.name).glob('kora-*.zip')))

    def test_batch_export_runs_independent_photos_concurrently(self):
        from unittest.mock import patch
        from kora.gui import RenderRequest
        library=Library([],self.scratch.name,capacity={"cpu_count":8,"physical_memory":16*1024**3,
                                                       "export_workers":2,"thumbnail_workers":4})
        requests=[]
        for name in ('one.DNG','two.DNG'):
            path=Path(self.scratch.name)/name;path.write_bytes(b'fixture')
            requests.append(RenderRequest(id=library.add(path)['id'],recipe=StudioRecipe()))
        barrier=threading.Barrier(2);active=0;peak=0;guard=threading.Lock()
        def develop(request):
            nonlocal active,peak
            with guard:active+=1;peak=max(peak,active)
            barrier.wait(timeout=1)
            with guard:active-=1
            return request.id.encode(),'image/jpeg'
        with patch.object(library,'_develop_batch_item',side_effect=develop):
            archive=library.export_jpeg_archive(requests)
        try:self.assertEqual(peak,2)
        finally:archive.unlink(missing_ok=True)

    def test_heavy_batch_reduces_image_workers_to_avoid_memory_pressure(self):
        from kora.gui import RenderRequest
        library=Library([],self.scratch.name,capacity={"cpu_count":14,"physical_memory":36*1024**3,
                                                       "export_workers":4,"thumbnail_workers":7})
        light=[RenderRequest(id=str(i),recipe=StudioRecipe()) for i in range(4)]
        heavy=[RenderRequest(id=str(i),recipe=StudioRecipe(highlights=-50,clarity=2,
               grain='strong',color_chrome='strong',lens_distortion='auto')) for i in range(4)]
        self.assertEqual(library.batch_export_workers(light),4)
        self.assertEqual(library.batch_export_workers(heavy),2)

    def test_batch_export_reuses_active_full_resolution_decode(self):
        from unittest.mock import patch
        from kora.gui import RenderRequest
        import numpy as np
        path=Path(self.scratch.name)/'cached.DNG';path.write_bytes(b'fixture')
        item=self.server.library.add(path)
        cached=np.ones((12,18,3),np.float32)
        self.server.library.linear_cache[item['id']]=cached
        request=RenderRequest(id=item['id'],recipe=StudioRecipe())
        with patch('kora.gui.decode',side_effect=AssertionError('decode should be reused')), \
             patch('kora.gui.render',side_effect=lambda pixels,*args,**kwargs:pixels) as renderer, \
             patch('kora.gui.encode',return_value=(b'jpeg','image/jpeg')):
            self.assertEqual(self.server.library._develop_batch_item(request),(b'jpeg','image/jpeg'))
        self.assertIs(renderer.call_args.args[0],cached)

    def test_idle_prefetch_populates_the_same_full_resolution_export_cache(self):
        from unittest.mock import patch
        from kora.gui import RenderRequest
        import numpy as np
        capacity={"cpu_count":8,"physical_memory":16*1024**3,"export_workers":2,
                  "thumbnail_workers":4,"full_resolution_prefetch":True}
        library=Library([],self.scratch.name,capacity=capacity)
        path=Path(self.scratch.name)/'prefetch.DNG';path.write_bytes(b'fixture')
        item=library.add(path);pixels=np.ones((12,18,3),np.float32)
        request=RenderRequest(id=item['id'],recipe=StudioRecipe())
        with patch('kora.gui.decode',return_value=pixels) as decoder:
            self.assertTrue(library.prefetch(item['id']))
        decoder.assert_called_once_with(Path(item['path']),preview=False)
        with patch('kora.gui.decode',side_effect=AssertionError('decode should be reused')), \
             patch('kora.gui.source_details',return_value={}), \
             patch('kora.gui.render',side_effect=lambda value,*args,**kwargs:value), \
             patch('kora.gui.encode',return_value=(b'jpeg','image/jpeg')):
            self.assertEqual(library.develop(request,export=True),(b'jpeg','image/jpeg'))

    def test_idle_prefetch_is_disabled_on_memory_constrained_hosts(self):
        from unittest.mock import patch
        library=Library([],self.scratch.name,capacity={"cpu_count":4,"physical_memory":8*1024**3,
            "export_workers":1,"thumbnail_workers":2,"full_resolution_prefetch":False})
        with patch.object(library,'full_linear') as full_linear:
            self.assertFalse(library.prefetch('unused'))
        full_linear.assert_not_called()

    def test_batch_export_rejects_non_jpeg_and_duplicate_photos(self):
        path=Path(self.scratch.name)/'batch.DNG';path.write_bytes(b'fixture')
        item=self.server.library.add(path)
        tiff=json.dumps({'items':[{'id':item['id'],'recipe':{'file_type':'tiff8'}},{'id':'missing','recipe':{}}]})
        duplicate=json.dumps({'items':[{'id':item['id'],'recipe':{}},{'id':item['id'],'recipe':{}}]})
        self.assertEqual(self.request('/api/export-batch','POST',tiff)[0],422)
        self.assertEqual(self.request('/api/export-batch','POST',duplicate)[0],422)

    def test_optics_are_applied_to_preview_and_export_without_mutating_cache(self):
        from unittest.mock import patch
        import numpy as np
        from kora.gui import RenderRequest
        from kora.studio import StudioRecipe
        from kora.optics import apply_corrections
        path=Path(self.scratch.name)/'geometry.DNG';path.write_bytes(b'fixture')
        item=self.server.library.add(path)
        a=np.random.default_rng(10).uniform(0,3,(48,64,3)).astype(np.float32)
        saved=a.copy()
        profile={'orientation':1,'source':'dng-warp','distortion':True,
                 'warp':{'center':[.5,.5],'coefficients':[1,-.1,0,0,0,0]}}
        expected=apply_corrections(a,profile,'auto')
        request=RenderRequest(id=item['id'],recipe=StudioRecipe(lens_distortion='auto'))
        with patch('kora.optics.inspect_optics',return_value=profile), \
             patch('kora.gui.decode',return_value=a.copy()) as decoder, \
             patch('kora.gui.render',side_effect=lambda pixels,*args,**kwargs:pixels) as renderer, \
             patch('kora.gui.encode',return_value=(b'encoded','image/jpeg')):
            for export in (False,True):
                self.server.library.develop(request,export=export)
                np.testing.assert_allclose(renderer.call_args.args[0],expected)
        self.assertEqual([call.kwargs["preview"] for call in decoder.call_args_list],[False])
        np.testing.assert_array_equal(self.server.library.linear_cache[item['id']],saved)
        np.testing.assert_array_equal(a,saved)

    def test_interactive_preview_uses_reduced_decode_without_filling_full_cache(self):
        from unittest.mock import patch
        import numpy as np
        from kora.gui import RenderRequest
        from kora.studio import StudioRecipe
        path=Path(self.scratch.name)/'fast.DNG';path.write_bytes(b'fixture')
        item=self.server.library.add(path);pixels=np.ones((32,48,3),np.float32)
        request=RenderRequest(id=item['id'],recipe=StudioRecipe(),quality='interactive')
        with patch('kora.gui.decode',return_value=pixels) as decoder, \
             patch('kora.gui.render',side_effect=lambda *args,**kwargs:self._assert_decoder_released(pixels)), \
             patch('kora.gui.encode',return_value=(b'preview','image/jpeg')):
            self.server.library.develop(request)
        decoder.assert_called_once_with(Path(item['path']),preview=True)
        self.assertNotIn(item['id'],self.server.library.linear_cache)

    def _assert_decoder_released(self, pixels):
        acquired=self.server.library.decoder_lock.acquire(blocking=False)
        self.assertTrue(acquired,"The LibRaw lock must not cover rendering")
        if acquired:self.server.library.decoder_lock.release()
        return pixels

    def test_interactive_edit_overtakes_full_resolution_render(self):
        from unittest.mock import patch
        import numpy as np
        from kora.gui import RenderRequest
        from kora.studio import StudioRecipe
        path=Path(self.scratch.name)/'overtake.DNG';path.write_bytes(b'fixture')
        item=self.server.library.add(path)
        full=np.ones((64,96,3),np.float32)
        reduced=np.full((24,36,3),.5,np.float32)
        self.server.library.linear_cache[item['id']]=full
        started=threading.Event();release=threading.Event();interactive_done=threading.Event()

        def renderer(pixels,*args,**kwargs):
            if pixels is full:
                started.set();self.assertTrue(release.wait(2))
            else:
                interactive_done.set()
            return pixels

        full_request=RenderRequest(id=item['id'],recipe=StudioRecipe(),quality='full')
        quick_request=RenderRequest(id=item['id'],recipe=StudioRecipe(),quality='interactive')
        with patch('kora.gui.decode',return_value=reduced), \
             patch('kora.gui.render',side_effect=renderer), \
             patch('kora.gui.encode',return_value=(b'image','image/jpeg')):
            worker=threading.Thread(target=self.server.library.develop,args=(full_request,))
            worker.start();self.assertTrue(started.wait(1))
            quick=threading.Thread(target=self.server.library.develop,args=(quick_request,))
            quick.start();self.assertTrue(interactive_done.wait(1))
            release.set();quick.join(1);worker.join(1)
        self.assertFalse(quick.is_alive());self.assertFalse(worker.is_alive())

    def test_export_pauses_new_source_detail_renders(self):
        from unittest.mock import patch
        import numpy as np
        from kora.gui import RenderRequest
        path=Path(self.scratch.name)/'priority.DNG';path.write_bytes(b'fixture')
        item=self.server.library.add(path);pixels=np.ones((360,540,3),np.float32)
        self.server.library.linear_cache[item['id']]=pixels
        started=threading.Event();release=threading.Event()
        def renderer(source,*args,**kwargs):
            if kwargs.get('output_transform',True):
                started.set();self.assertTrue(release.wait(2))
            return source
        request=RenderRequest(id=item['id'],recipe=StudioRecipe())
        tile=TileRequest(id=item['id'],recipe=StudioRecipe(),x=0,y=0,size=128)
        with patch('kora.gui.render',side_effect=renderer), \
             patch('kora.gui.encode',return_value=(b'image','image/jpeg')):
            worker=threading.Thread(target=self.server.library.develop,args=(request,True))
            worker.start();self.assertTrue(started.wait(1))
            with self.assertRaisesRegex(ValueError,'paused during export'):
                self.server.library.render_tile(tile)
            release.set();worker.join(1)
        self.assertFalse(worker.is_alive())

    def test_startup_uses_folder_shortcuts_without_scanning_photos(self):
        root=Path(self.scratch.name)
        (root/'photo.DNG').write_bytes(b'fixture')
        library=Library([root],root)
        self.assertEqual(library.listing(),[])
        browser=library.folders()
        self.assertEqual(browser['path'],str(root.resolve()))
        self.assertIn(str(root.resolve()),[item['path'] for item in browser['shortcuts']])
        self.assertEqual(browser['raw_count'],1)
        self.assertEqual(browser['breadcrumbs'][-1]['path'],str(root.resolve()))
        self.assertEqual(library.listing(),[])

    def test_folder_rejects_malformed_input_and_cross_origin_access(self):
        for body in ('[]','null','{"path":""}','{"path":2}','{"path":"/","recursive":1}'):
            with self.subTest(body=body):
                self.assertEqual(self.request('/api/folder','POST',body)[0],422)
        self.assertEqual(self.request('/api/folder','POST','{}',{'Origin':'https://untrusted.example'})[0],403)
        self.assertEqual(self.request('/api/folders',headers={'X-Fuji-Session':''})[0],403)

    def test_busy_port_uses_another_loopback_port(self):
        other = bind_studio_server(self.server.server_port)
        try:
            self.assertNotEqual(other.server_port, self.server.server_port)
            self.assertEqual(other.server_address[0], '127.0.0.1')
        finally:
            other.server_close()

    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        from unittest.mock import patch
        self.log_patch = patch('kora.diagnostics.log_path', return_value=Path(self.scratch.name)/'errors.jsonl')
        self.log_patch.start()
        self.addCleanup(self.log_patch.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.session_token = "unit-test-session"
        self.server.library = Library([], self.scratch.name)
        self.worker = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()
        self.scratch.cleanup()

    def request(self, path, method="GET", body=None, headers=None):
        client = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        client.request(method, path, body, {"X-Fuji-Session": self.server.session_token, **(headers or {})})
        response = client.getresponse()
        code, data = response.status, response.read()
        client.close()
        return code, json.loads(data) if response.getheader("Content-Type", "").startswith("application/json") else data

    def test_library_is_private_to_local_session(self):
        for headers in [{"X-Fuji-Session": "wrong"}, {"Origin": "https://untrusted.example"}, {"Host": "untrusted.example"}]:
            with self.subTest(headers=headers):
                self.assertEqual(self.request("/api/library", headers=headers)[0], 403)
        code, data = self.request("/api/library")
        self.assertEqual(code, 200)
        self.assertEqual(data["files"], [])
        self.assertTrue(data["engine"]["available"])
        self.assertFalse(data["engine"]["exact_fuji_render"])

    def test_diagnostics_are_authenticated_and_persist_safe_context(self):
        body = json.dumps({'operation':'zoom', 'message':'Tile failed', 'stack':'app.js:382',
                           'context':{'photo_id':'abc','zoom':4,'recipe':{'name':'private'}}})
        self.assertEqual(self.request('/api/diagnostics','POST',body,{'X-Fuji-Session':'wrong'})[0],403)
        code, result = self.request('/api/diagnostics','POST',body)
        self.assertEqual(code,200)
        self.assertTrue(result['recorded'])
        events=[json.loads(line) for line in (Path(self.scratch.name)/'errors.jsonl').read_text().splitlines()]
        event=events[-1]
        self.assertEqual(event['operation'],'client.zoom')
        self.assertEqual(event['context'],{'photo_id':'abc','zoom':4})
        self.assertNotIn('private',json.dumps(event))

    def test_api_exception_has_correlated_traceback(self):
        from unittest.mock import patch
        with patch.object(self.server.library,'render_tile',side_effect=RuntimeError('tile test')):
            code,result=self.request('/api/tile','POST',json.dumps({'id':'abc','recipe':{},'x':0,'y':0}),
                                     {'X-Film-Request-ID':'request-test'})
        self.assertEqual(code,422)
        event=json.loads((Path(self.scratch.name)/'errors.jsonl').read_text().splitlines()[-1])
        self.assertEqual(event['id'],result['error_id'])
        self.assertEqual(event['context']['request_id'],'request-test')
        self.assertEqual(event['context']['photo_id'],'abc')
        self.assertTrue(event['frames'])

    def test_recipe_roundtrip_and_invalid_input(self):
        code, data = self.request("/api/recipe", "POST", json.dumps({"name": "Test", "film": "acros", "highlights": -37, "whites": -12, "wb_red": 2}))
        self.assertEqual(code, 200)
        self.assertEqual(data["recipe"]["film"], "acros")
        self.assertEqual((data["recipe"]["highlights"],data["recipe"]["whites"]),(-37,-12))
        self.assertTrue(data["render_available"])
        self.assertEqual(self.request("/api/recipe", "POST", '{"unknown": 1}')[0], 422)

    def test_recipe_folder_indexes_valid_json_and_loads_by_server_id(self):
        folder=Path(self.scratch.name)/'recipes';folder.mkdir()
        (folder/'Kodachrome.json').write_text(json.dumps({'name':'Kodachrome','film':'classic_chrome','grain':'strong'}))
        (folder/'Broken.json').write_text('{not json')
        (folder/'notes.txt').write_text('{}')
        code,data=self.request('/api/recipes/folder','POST',json.dumps({'path':str(folder)}))
        self.assertEqual(code,200)
        self.assertEqual(data['folder'],str(folder.resolve()))
        self.assertEqual(data['invalid_count'],1)
        self.assertEqual([(item['name'],item['filename']) for item in data['recipes']],
                         [('Kodachrome','Kodachrome.json')])
        code,loaded=self.request('/api/recipes/load','POST',json.dumps({'id':data['recipes'][0]['id']}))
        self.assertEqual(code,200)
        self.assertEqual(loaded['recipe']['film'],'classic_chrome')
        self.assertEqual(loaded['recipe']['grain'],'strong')

    def test_recipe_folder_rejects_unknown_ids_symlinks_and_large_json(self):
        folder=Path(self.scratch.name)/'recipes';folder.mkdir()
        outside=Path(self.scratch.name)/'outside.json';outside.write_text(json.dumps({'name':'Outside'}))
        try:(folder/'Outside.json').symlink_to(outside)
        except OSError:pass
        (folder/'Large.json').write_bytes(b'{' + b' '*(64*1024) + b'}')
        code,data=self.request('/api/recipes/folder','POST',json.dumps({'path':str(folder)}))
        self.assertEqual(code,200)
        self.assertEqual(data['recipes'],[])
        self.assertEqual(data['invalid_count'],1)
        self.assertEqual(self.request('/api/recipes/load','POST',json.dumps({'id':'../../outside'}))[0],422)

    def test_fullscreen_is_native_only_and_requires_session(self):
        from unittest.mock import Mock
        self.assertFalse(self.request('/api/library')[1]['native_window'])
        self.assertEqual(self.request('/api/window/fullscreen', 'POST', '{}')[0], 409)
        self.server.toggle_fullscreen = Mock()
        self.assertTrue(self.request('/api/library')[1]['native_window'])
        for headers in ({'X-Fuji-Session': 'wrong'}, {'Origin': 'https://untrusted.example'}):
            self.assertEqual(self.request('/api/window/fullscreen', 'POST', '{}', headers)[0], 403)
        self.server.toggle_fullscreen.assert_not_called()
        self.assertEqual(self.request('/api/window/fullscreen', 'POST', '{}'), (200, {'ok': True}))
        self.server.toggle_fullscreen.assert_called_once()

    def test_render_requires_valid_photo_and_recipe(self):
        self.assertEqual(self.request("/api/render", "POST", "{}")[0], 422)
        self.assertEqual([p.name for p in Path(self.scratch.name).iterdir()], ['errors.jsonl'])

    def test_import_is_confined_to_generated_directory(self):
        from kora.gui import MAX_UPLOAD
        self.assertEqual(self.request("/api/import?name=photo.jpg", "POST", "not-raw")[0], 415)
        code, data = self.request("/api/import?name=..%2F..%2Fexample.RAF", "POST", "synthetic-unit-test")
        self.assertEqual(code, 201)
        path = Path(data["path"])
        self.assertTrue(path.is_relative_to(Path(self.scratch.name).resolve()))
        self.assertEqual(path.name, "example.RAF")
        self.assertEqual(path.read_text(), "synthetic-unit-test")
        self.assertEqual(self.request("/api/import?name=large.RAF", "POST", "", {"Content-Length": str(MAX_UPLOAD+1)})[0], 413)

    def test_lut_archive_is_verified_locally_then_deleted(self):
        from unittest.mock import patch
        observed=[]
        def install(path):
            self.assertTrue(path.is_file())
            self.assertTrue(path.resolve().is_relative_to(Path(self.scratch.name).resolve()))
            self.assertEqual(path.read_bytes(),b'synthetic ZIP fixture')
            observed.append(path)
        engine={'missing_luts':[]}
        with patch('kora.gui.install_archive',side_effect=install), \
             patch('kora.gui.studio_status',return_value=engine):
            code,data=self.request('/api/luts/install?name=official.zip','POST',b'synthetic ZIP fixture',
                                   {'Content-Type':'application/zip'})
        self.assertEqual(code,201)
        self.assertTrue(data['installed'])
        self.assertEqual(data['engine'],engine)
        self.assertEqual(len(observed),1)
        self.assertFalse(observed[0].exists())
        self.assertEqual(self.request('/api/luts/install?name=profile.cube','POST',b'not a zip')[0],415)

    def test_lut_folder_installation(self):
        from unittest.mock import patch
        folder = Path(self.scratch.name)/'extracted-luts'
        folder.mkdir()
        with patch('kora.gui.install_archive') as install, patch('kora.gui.studio_status', return_value={'missing_luts':[]}):
            code, data = self.request('/api/luts/install', 'POST', json.dumps({'path':str(folder)}), {'Content-Type':'application/json'})
        self.assertEqual(code, 201)
        self.assertTrue(data['installed'])
        install.assert_called_once_with(folder)
        self.assertTrue(folder.exists())

    def test_folder_selection_reads_originals_without_copying(self):
        root=Path(self.scratch.name).resolve()/"photos";root.mkdir()
        (root/"a.CR3").write_bytes(b"raw fixture")
        (root/"b.jpg").write_bytes(b"jpeg fixture")
        sub=root/"sub";sub.mkdir();(sub/"c.DNG").write_bytes(b"dng fixture")
        from urllib.parse import quote
        code,data=self.request("/api/folders?path="+quote(str(root)))
        self.assertEqual(code,200)
        self.assertEqual(data["folders"],[{"name":"sub","path":str(sub)}])
        self.assertEqual(data["raw_count"],1)
        self.assertEqual(data["breadcrumbs"][-1],[{"name":"photos","path":str(root)}][0])
        for recursive,count in [(False,1),(True,2)]:
            code,data=self.request("/api/folder","POST",json.dumps({"path":str(root),"recursive":recursive}))
            self.assertEqual(code,200);self.assertEqual(len(data["files"]),count)
            self.assertEqual(data["files"][0]["path"],str(root/"a.CR3"))
        self.assertEqual(len(list(root.rglob("*"))),4)
        self.assertEqual(self.request("/api/folder","POST",json.dumps({"path":str(root),"recursive":"false"}))[0],422)
        self.assertEqual(self.request("/api/folders?path="+quote(str(root)),headers={"X-Fuji-Session":"wrong"})[0],403)

    def test_raw_import_streams_data_and_rejects_an_oversized_body_before_reading(self):
        from kora.gui import MAX_UPLOAD
        payload=bytes(range(256))*8192+b'RAW end'
        code,item=self.request('/api/import?name=medium-format.3FR','POST',payload)
        self.assertEqual(code,201)
        self.assertEqual(Path(item['path']).read_bytes(),payload)
        self.assertEqual(item['format'],'3FR')
        count=len(self.server.library.files)
        code,error=self.request('/api/import?name=too-large.3FR','POST',b'',
                                {'Content-Length':str(MAX_UPLOAD+1)})
        self.assertEqual(code,413)
        self.assertIn('MiB',error['error'])
        self.assertEqual(len(self.server.library.files),count)

    def test_unsupported_nikon_compression_has_actionable_error(self):
        from unittest.mock import patch
        import rawpy
        path=Path(self.scratch.name)/'unsupported.NEF';path.write_bytes(b'fixture')
        item=self.server.library.add(path)
        for compression in ('High Efficiency','High Efficiency*'):
            with self.subTest(compression=compression), \
                 patch('kora.gui.exif',return_value={'Make':'NIKON CORPORATION','Model':'NIKON Z 8','NEFCompression':compression}), \
                 patch('kora.gui.rawpy.imread',side_effect=rawpy.LibRawFileUnsupportedError('Unsupported')):
                code,error=self.request('/api/photo/'+item['id'])
                self.assertEqual(code,422)
                self.assertIn('HE/HE*',error['error'])
                self.assertIn('lossless-compressed',error['error'])
                self.assertIn('DNG',error['error'])
                self.assertNotIn('b\'',error['error'])

    def test_unsupported_raw_without_metadata_does_not_guess_nikon(self):
        from unittest.mock import patch
        import rawpy
        path=Path(self.scratch.name)/'unsupported.ARW';path.write_bytes(b'fixture')
        item=self.server.library.add(path)
        with patch('kora.gui.exif',return_value={'metadata_available':False}), \
             patch('kora.gui.rawpy.imread',side_effect=rawpy.LibRawFileUnsupportedError('Unsupported')):
            code,error=self.request('/api/photo/'+item['id'])
        self.assertEqual(code,422)
        self.assertIn('not supported',error['error'])
        self.assertNotIn('Nikon',error['error'])

    def test_unsupported_compression_reported_when_metadata_opens_but_development_fails(self):
        from unittest.mock import patch,MagicMock
        import rawpy
        path=Path(self.scratch.name)/'unsupported.NEF';path.write_bytes(b'fixture')
        item=self.server.library.add(path)
        raw=MagicMock();raw.__enter__.return_value=raw
        raw.sizes.width=100;raw.sizes.height=80;raw.sizes.flip=0
        raw.sizes._asdict.return_value={'width':100,'height':80,'flip':0}
        raw.extract_thumb.side_effect=rawpy.LibRawNoThumbnailError('No thumbnail')
        with patch('kora.gui.exif',return_value={'Make':'NIKON','NEFCompression':'High Efficiency'}), \
             patch('kora.gui.rawpy.imread',return_value=raw), \
             patch('kora.studio.source_details',side_effect=rawpy.LibRawFileUnsupportedError('Unsupported')):
            code,error=self.request('/api/photo/'+item['id'])
        self.assertEqual(code,422)
        self.assertIn('HE/HE*',error['error'])

    @unittest.skipIf(missing_luts(), "Official LUT integration: install Fuji assets separately")
    def test_render_endpoint_applies_recipe_to_cached_raw_pixels(self):
        import numpy as np
        from PIL import Image
        from io import BytesIO
        path=Path(self.scratch.name)/"cached.DNG"
        path.write_bytes(b"test fixture; decoder output injected below")
        item=self.server.library.add(path)
        self.server.library.linear_cache[item["id"]]=np.full((32,48,3),.15,dtype=np.float32)
        images=[]
        for exposure in [0,1]:
            code,data=self.request("/api/render","POST",json.dumps({"id":item["id"],"recipe":{"exposure":exposure}}))
            self.assertEqual(code,200)
            images.append(np.asarray(Image.open(BytesIO(data))).astype(float))
        self.assertGreater(images[1].mean(),images[0].mean()+20)
