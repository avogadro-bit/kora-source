from io import BytesIO
from pathlib import Path
import json
import unittest
from unittest.mock import patch
import numpy as np
import tifffile
from PIL import Image
from pydantic import ValidationError
from kora.kodachrome import apply_kodachrome, load_model
from kora.recipe import Recipe
from kora.studio import StudioRecipe, render, encode


class KodachromeTests(unittest.TestCase):
    def test_matches_independent_spectral_reference(self):
        fixture=json.loads((Path(__file__).with_name('data')/'kodachrome_reference.json').read_text())
        rgb=np.asarray(fixture['rgb'],np.float32)[:,None,:]
        for ev,truth in zip(fixture['exposures'],fixture['display_srgb']):
            with self.subTest(ev=ev):
                got=render(rgb,StudioRecipe(film='kodachrome64',exposure=ev))[:,0]
                error=np.abs(got-np.asarray(truth))
                self.assertLess(float(error.max()),.005)
                self.assertLess(float(np.percentile(error,99)),.002)

    def test_tiles_parallel_and_single_render_agree_without_mutating_source(self):
        rgb=np.random.default_rng(16).uniform(-.1,3,(545,39,3)).astype(np.float32)
        original=rgb.copy();recipe=StudioRecipe(film='kodachrome64',exposure=.7)
        full=render(rgb,recipe,output_transform=False)
        tiles=np.concatenate([render(rgb[a:b],recipe,output_transform=False,origin=(a,0)) for a,b in ((0,73),(73,219),(219,545))])
        np.testing.assert_array_equal(rgb,original)
        np.testing.assert_array_equal(full,tiles)
        np.testing.assert_array_equal(apply_kodachrome(rgb,.7,workers=1),apply_kodachrome(rgb,.7,workers=4))
        self.assertTrue(np.isfinite(full).all())
        self.assertGreaterEqual(full.min(),0);self.assertLessEqual(full.max(),1)

    def test_gray_exposure_brightens_and_hdr_keeps_headroom(self):
        rgb=np.full((1,1,3),.18,np.float32)
        dark=render(rgb,StudioRecipe(film='kodachrome64',exposure=-1))
        bright=render(rgb,StudioRecipe(film='kodachrome64',exposure=1))
        self.assertTrue(np.all(bright>dark))
        hdr=np.repeat(np.array([.8,1.,1.2,1.8])[:,None,None],3,axis=2)
        values=render(hdr,StudioRecipe(film='kodachrome64',exposure=-1))
        self.assertTrue(np.all(np.diff(values[:,0,1])>0))
        edge=np.array([[[1.-1e-6,.7,.3],[1.+1e-6,.7,.3]]])
        self.assertLess(np.abs(np.diff(apply_kodachrome(edge),axis=1)).max(),1e-4)

    def test_film_is_separate_from_native_fuji_and_roundtrips(self):
        recipe=StudioRecipe(film='kodachrome64')
        self.assertEqual(StudioRecipe.model_validate_json(recipe.model_dump_json()),recipe)
        with self.assertRaises(ValidationError):Recipe(film='kodachrome64')
        self.assertEqual(StudioRecipe().film,'provia')
        with patch('kora.studio.apply_official',side_effect=AssertionError('No Fuji LUT dependency')):
            render(np.full((5,5,3),.18),recipe)

    def test_tiff16_metadata_and_jpeg_identify_experimental_film(self):
        recipe=StudioRecipe(film='kodachrome64',file_type='tiff16')
        pixels=render(np.full((4,3,3),.18),recipe)
        data,mime=encode(pixels,recipe)
        self.assertEqual(mime,'image/tiff')
        with tifffile.TiffFile(BytesIO(data)) as image:
            self.assertEqual(image.asarray().dtype,np.uint16)
            meta=json.loads(image.pages[0].description)
            self.assertEqual(meta['renderer'],'kodachrome64-spectral-v1')
            self.assertTrue(meta['experimental']);self.assertIsNone(meta['official_lut'])
            self.assertEqual(meta['kodachrome']['sha256'],load_model()[1]['sha256'])
            self.assertIn(34675,image.pages[0].tags)
        data,_=encode(pixels,recipe.model_copy(update={'file_type':'jpeg'}))
        self.assertIn(b'experimental Kodachrome 64',Image.open(BytesIO(data)).info['comment'])

    def test_rejects_nonfinite_input(self):
        for value in (np.nan,np.inf):
            with self.assertRaises(ValueError):apply_kodachrome(np.full((1,1,3),value))

    def test_raw_base_works_without_optional_fuji_assets(self):
        from kora.studio import _preview_source
        from kora.official_luts import MissingLUTError
        _preview_source.cache_clear()
        pixels=np.full((12,12,3),.18,np.float32)
        with patch('kora.studio.exif',return_value={}), \
             patch('kora.studio._decode_sensor',return_value=(pixels.copy(),pixels.copy())), \
             patch('kora.studio.apply_official',side_effect=MissingLUTError('missing')):
            base,info=_preview_source(Path('test.DNG'),0,0)
            self.assertFalse(info['reference_matched'])
            self.assertEqual(info['reference_ev'],0.)
            np.testing.assert_array_equal(base,pixels)
            self.assertTrue(np.isfinite(render(base,StudioRecipe(film='kodachrome64'))).all())
        _preview_source.cache_clear()
