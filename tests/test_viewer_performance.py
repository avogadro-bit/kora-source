from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image, JpegImagePlugin
from kora.gui import Library, RenderRequest
from kora.studio import StudioRecipe, _preview_source


class ViewerPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.library=Library([self.root],self.root,capacity={
            'physical_memory':32*1024**3,'export_workers':2,
            'thumbnail_workers':2,'full_resolution_prefetch':True})
        self.ids=[]
        for name in ['a.DNG','b.DNG','c.DNG']:
            path=self.root/name;path.write_bytes(b'fixture')
            self.ids.append(self.library.add(path)['id'])

    def tearDown(self):
        self.temp.cleanup()

    def test_display_uses_full_raw_and_reuses_completed_recipe_only(self):
        source=np.random.default_rng(4).uniform(0,.6,(600,900,3)).astype(np.float32)
        saved=source.copy()
        request=RenderRequest(id=self.ids[0],recipe=StudioRecipe(aspect='1:1'),quality='display',edge=512,neutral=True)
        with patch('kora.gui.decode',return_value=source) as decoder, patch('kora.gui.render_context',return_value={}):
            payload,mime=self.library.develop(request)
            repeated=self.library.develop(request)
            self.assertEqual(repeated,(payload,mime))
            image=Image.open(BytesIO(payload))
            self.assertEqual(image.size,(512,512))
            self.assertEqual(JpegImagePlugin.get_sampling(image),0)
            self.assertIn('icc_profile',image.info)
            decoder.assert_called_once_with(Path(self.library.files[self.ids[0]]['path']),preview=False)
            other=self.library.develop(request.model_copy(update={'recipe':StudioRecipe(aspect='16:9')}))
            self.assertNotEqual(other[0],payload)
            self.library.develop(request.model_copy(update={'edge':600}))
            self.assertEqual(len(self.library.display_cache),3)
        np.testing.assert_array_equal(source,saved)

    def test_cached_zoom_does_not_wait_for_neighbour_decode(self):
        library=self.library;pixels=np.ones((12,18,3),np.float32)
        library.linear_cache[self.ids[0]]=pixels
        started=threading.Event();release=threading.Event()
        def decode(*args,**kwargs):
            started.set();self.assertTrue(release.wait(3));return pixels.copy()
        with patch('kora.gui.decode',side_effect=decode),ThreadPoolExecutor(max_workers=2) as pool:
            neighbour=pool.submit(library.prefetch,self.ids[1],self.ids[0])
            try:
                self.assertTrue(started.wait(1))
                active=pool.submit(library.full_linear,self.ids[0])
                self.assertIs(active.result(timeout=1),pixels)
            finally:release.set()
            self.assertTrue(neighbour.result(timeout=2))

    def test_cache_budget_protects_active_photo_during_prefetch(self):
        library=self.library;pixels=np.ones((12,18,3),np.float32)
        library.linear_cache_budget=pixels.nbytes*2
        with patch('kora.gui.decode',side_effect=lambda *a,**k:pixels.copy()):
            library.full_linear(self.ids[0]);library.full_linear(self.ids[1])
            self.assertTrue(library.prefetch(self.ids[2],self.ids[0]))
            self.assertEqual(set(library.linear_cache),{self.ids[0],self.ids[2]})
            library.linear_cache_budget=pixels.nbytes
            self.assertFalse(library.prefetch(self.ids[1],self.ids[0]))
            self.assertEqual(list(library.linear_cache),[self.ids[0]])

    def test_concurrent_inspection_and_full_decode_share_exposure_anchor(self):
        _preview_source.cache_clear()
        started=threading.Event();release=threading.Event()
        def sensor(*a,**k):
            started.set();self.assertTrue(release.wait(3))
            return np.full((24,32,3),.1,np.float32),None
        path=self.root/'a.DNG'
        with patch('kora.studio.exif',return_value={}),patch('kora.studio._decode_sensor',side_effect=sensor) as decoder,ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(_preview_source,path,0,0)
            try:
                self.assertTrue(started.wait(1))
                second=pool.submit(_preview_source,path,0,0)
            finally:release.set()
            self.assertIs(first.result(timeout=2),second.result(timeout=2))
            self.assertEqual(decoder.call_count,1)
        _preview_source.cache_clear()
