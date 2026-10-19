"""Memory bounds and pixel invariance for display and batch scheduling."""
from concurrent.futures import Future, ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import weakref
import zipfile

import numpy as np
from PIL import Image

from kora.gui import Library, RenderRequest
from kora.studio import StudioRecipe, _resize_float_to


class ImmediatePool:
    """Completed jobs expose retained results without timing-dependent races."""
    def __init__(self, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def submit(self, function, argument):
        future = Future()
        try:
            future.set_result(function(argument))
        except BaseException as error:
            future.set_exception(error)
        return future


class GuiPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.library = Library([self.root], self.root, capacity={
            'physical_memory': 8*1024**3, 'export_workers': 1,
            'thumbnail_workers': 2, 'full_resolution_prefetch': False})
        self.path = self.root/'sample.DNG'
        self.path.write_bytes(b'local fixture')
        self.identifier = self.library.add(self.path)['id']
        self.source = np.random.default_rng(12).uniform(-.05, 1.5, (480, 720, 3)).astype(np.float32)
        self.library.linear_cache[self.identifier] = self.source

    def tearDown(self):
        self.temp.cleanup()

    def test_slider_changes_reuse_reduction_without_changing_pixels(self):
        saved = self.source.copy()
        requests = [RenderRequest(id=self.identifier, quality='display', edge=512,
                    recipe=StudioRecipe(film='kodachrome64', exposure=exposure))
                    for exposure in (0., .25, -.5)]
        # The uncached path is the previous implementation's calculation.
        with patch('kora.gui.render_context', return_value={}):
            self.library.display_source_budget = 0
            expected = [self.library.display_preview(request)[0] for request in requests]
            self.library.display_cache.clear()
            self.library.display_source_budget = 32*1024**2
            with patch('kora.gui._resize_float_to', wraps=_resize_float_to) as resize:
                actual = [self.library.display_preview(request)[0] for request in requests]
            self.assertEqual(resize.call_count, 1)
        for before, after in zip(expected, actual):
            np.testing.assert_array_equal(np.asarray(Image.open(BytesIO(before))),
                                          np.asarray(Image.open(BytesIO(after))))
        np.testing.assert_array_equal(self.source, saved)
        cached = next(iter(self.library.display_source_cache.values()))
        self.assertFalse(cached.flags.writeable)
        self.assertFalse(np.shares_memory(cached, self.source))

    def test_display_reduction_changes_with_size_and_source_fingerprint(self):
        request = RenderRequest(id=self.identifier, quality='display', edge=512,
                                neutral=True, recipe=StudioRecipe())
        with patch('kora.gui.render_context', return_value={}), \
             patch('kora.gui._resize_float_to', wraps=_resize_float_to) as resize:
            self.library.display_preview(request)
            self.library.display_preview(request.model_copy(update={'edge':600}))
            self.path.write_bytes(b'changed local fixture')
            self.library.display_preview(request)
            self.assertEqual(resize.call_count, 3)

    def test_optics_changes_reuse_only_uncorrected_pixels(self):
        saved = self.source.copy()
        profile = {'source':'dng-warp', 'orientation':1, 'distortion':True,
                   'warp':{'coefficients':[1,-.1,0,0,0,0], 'center':[.5,.5]}}
        plain = RenderRequest(id=self.identifier, quality='display', edge=512,
                              neutral=True, recipe=StudioRecipe())
        corrected = plain.model_copy(update={'recipe':StudioRecipe(lens_distortion='auto')})
        with patch('kora.gui.render_context', return_value={}), \
             patch('kora.optics.inspect_optics', return_value=profile), \
             patch('kora.gui._resize_float_to', wraps=_resize_float_to) as resize:
            plain_image = self.library.display_preview(plain)[0]
            corrected_image = self.library.display_preview(corrected)[0]
            self.assertEqual(resize.call_count, 1)
            self.assertNotEqual(plain_image, corrected_image)
            self.library.display_cache.clear()
            repeated = self.library.display_preview(plain)[0]
            np.testing.assert_array_equal(np.asarray(Image.open(BytesIO(repeated))),
                                          np.asarray(Image.open(BytesIO(plain_image))))
        np.testing.assert_array_equal(self.source, saved)

    def test_reduced_cache_has_byte_bound_and_never_retains_full_raw_view(self):
        size = (180, 120)
        self.library.display_source_budget = 180*120*3*4
        for key in range(4):
            self.library.display_linear(self.source, size, key)
        self.assertEqual(list(self.library.display_source_cache), [3])
        self.assertLessEqual(sum(value.nbytes for value in self.library.display_source_cache.values()),
                             self.library.display_source_budget)
        self.library.display_linear(self.source, (360, 240), 'oversize')
        self.library.display_linear(self.source, (720, 480), 'original')
        self.assertEqual(list(self.library.display_source_cache), [3])
        self.assertTrue(self.source.flags.writeable)

    def test_simultaneous_reductions_are_coalesced(self):
        started, release = threading.Event(), threading.Event()
        def slow_resize(*args):
            started.set()
            self.assertTrue(release.wait(3))
            return _resize_float_to(*args)
        with patch('kora.gui._resize_float_to', side_effect=slow_resize) as resize, \
             ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.library.display_linear, self.source, (180,120), 'same')
            try:
                self.assertTrue(started.wait(1))
                second = pool.submit(self.library.display_linear, self.source, (180,120), 'same')
            finally:
                release.set()
            self.assertIs(first.result(timeout=2), second.result(timeout=2))
            self.assertEqual(resize.call_count, 1)

    def test_batch_bounds_completed_jpegs_and_preserves_every_archive_entry(self):
        references, peak, requests = [], [0], []
        for index in range(32):
            path = self.root/f'photo-{index}.DNG'
            path.write_bytes(b'local fixture')
            requests.append(RenderRequest(id=self.library.add(path)['id'], recipe=StudioRecipe()))
        def develop(request):
            index = requests.index(request)
            # A byte-compatible, weak-referenceable array lets us measure
            # actual lifetime of each result, not merely the pending count.
            payload = np.full(1024, index, np.uint8)
            references.append(weakref.ref(payload))
            peak[0] = max(peak[0], sum(ref() is not None for ref in references))
            return payload, 'image/jpeg'
        with patch.object(self.library, '_develop_batch_item', side_effect=develop), \
             patch.object(self.library, 'batch_export_workers', return_value=2), \
             patch('kora.gui.ThreadPoolExecutor', ImmediatePool):
            archive_path = self.library.export_jpeg_archive(requests)
        self.assertLessEqual(peak[0], 2)
        self.assertTrue(all(ref() is None for ref in references))
        with zipfile.ZipFile(archive_path) as archive:
            self.assertEqual(len(archive.namelist()), 32)
            for index in range(32):
                self.assertEqual(archive.read(f'photo-{index}-provia.jpg'), bytes([index])*1024)

    def test_failed_batch_removes_archive_and_does_not_start_every_remaining_raw(self):
        requests = []
        for index in range(12):
            path = self.root/f'failure-{index}.DNG'
            path.write_bytes(b'local fixture')
            requests.append(RenderRequest(id=self.library.add(path)['id'], recipe=StudioRecipe()))
        def develop(request):
            if request is requests[0]:
                raise ValueError('decoder failure')
            return b'jpeg', 'image/jpeg'
        with patch.object(self.library, '_develop_batch_item', side_effect=develop) as worker, \
             patch.object(self.library, 'batch_export_workers', return_value=2), \
             patch('kora.gui.ThreadPoolExecutor', ImmediatePool):
            with self.assertRaisesRegex(ValueError, 'decoder failure'):
                self.library.export_jpeg_archive(requests)
        self.assertLessEqual(worker.call_count, 3)
        self.assertEqual(list(self.root.glob('*.zip')), [])


if __name__ == '__main__':
    unittest.main()
