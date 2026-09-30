from kora.official_luts import missing_luts
from io import BytesIO
from pathlib import Path
import unittest
import numpy as np
from PIL import Image, ImageCms
import tifffile
from pydantic import ValidationError
from kora.studio import StudioRecipe, render, encode, srgb_decode, large_radius_blur
from scipy.ndimage import gaussian_filter

@unittest.skipIf(missing_luts(), 'Official LUT integration: install Fuji assets separately')
class StudioTests(unittest.TestCase):
    def setUp(self):
        x=np.linspace(.02,.8,96,dtype=np.float32)
        self.a=np.stack([*np.meshgrid(x,x)[::-1],np.tile(x[::-1],(96,1))],axis=-1)
        self.r=StudioRecipe()

    def test_pixels_change_without_mutating_source(self):
        saved=self.a.copy()
        baseline=render(self.a,self.r)
        changed=render(self.a,StudioRecipe(exposure=1,wb_red=3,shadows=60))
        np.testing.assert_array_equal(saved,self.a)
        self.assertGreater(float(np.mean(abs(baseline-changed))),.02)
        self.assertTrue(np.isfinite(changed).all())
        self.assertGreaterEqual(changed.min(),0)
        self.assertLessEqual(changed.max(),1)

    def test_provia_is_the_default_recipe(self):
        recipe=StudioRecipe()
        self.assertEqual(recipe.film,'provia')
        self.assertEqual(recipe.name,'PROVIA / Standard')
        self.assertEqual((recipe.version,recipe.highlights,recipe.whites,recipe.shadows,recipe.blacks),
                         (2,0,0,0,0))

    def test_v1_fuji_tones_migrate_to_four_way_editor_controls(self):
        recipe=StudioRecipe(version=1,highlights=-2,shadows=2)
        self.assertEqual((recipe.version,recipe.highlights,recipe.whites,recipe.shadows,recipe.blacks),
                         (2,-50,0,-50,0))

    def test_large_fine_original_export_preserves_developed_dimensions(self):
        rendered=render(self.a,StudioRecipe(image_size='L',aspect='original',digital_crop=1))
        data,mime=encode(rendered,StudioRecipe(file_type='jpeg',image_quality='fine',image_size='L',aspect='original',digital_crop=1))
        self.assertEqual(rendered.shape,self.a.shape)
        self.assertEqual(Image.open(BytesIO(data)).size,(self.a.shape[1],self.a.shape[0]))
        self.assertEqual(mime,'image/jpeg')

    def test_large_radius_blur_preserves_shape_dtype_and_constant_color(self):
        flat=np.empty((128,192,3),np.float32);flat[:]=[.1,.4,.8]
        result=large_radius_blur(flat,36)
        self.assertEqual((result.shape,result.dtype),(flat.shape,np.dtype(np.float32)))
        np.testing.assert_allclose(result,flat,atol=1e-6)

    def test_heavy_profile_parallel_rows_are_pixel_identical(self):
        from unittest.mock import patch
        source=np.random.default_rng(92).uniform(-.1,2,(512,64,3)).astype(np.float32)
        recipe=StudioRecipe(film='classic_chrome',wb_red=4,wb_blue=3,
            highlights=10,shadows=11,blacks=10,color=1,clarity=2,grain='weak',
            color_chrome='strong',fx_blue='weak')
        def serial(length,callback,workers=None,block_rows=128,min_rows=512):
            for start in range(0,length,block_rows):callback(start,min(start+block_rows,length))
        with patch('kora.official_luts.run_parallel_rows',side_effect=serial), \
             patch('kora.recipe_effects.run_parallel_rows',side_effect=serial), \
             patch('kora.studio.run_parallel_rows',side_effect=serial), \
             patch('kora.grain.run_parallel_rows',side_effect=serial):
            expected=render(source,recipe)
        np.testing.assert_array_equal(render(source,recipe),expected)

    def test_tile_context_matches_the_same_region_of_a_full_render(self):
        recipe=StudioRecipe(noise_reduction=-4,grain='off')
        full=render(self.a,recipe)
        region=self.a[16:80,16:80]
        tiled=render(region,recipe,output_transform=False,
                     context={'sample':self.a[::8,::8],'full_shape':self.a.shape},origin=(16,16))
        np.testing.assert_allclose(tiled,full[16:80,16:80],atol=2e-6)

    def test_effects_are_repeatable_and_monochrome_has_no_chroma(self):
        r=StudioRecipe(grain='strong',grain_size='large')
        np.testing.assert_array_equal(render(self.a,r),render(self.a,r))
        mono=render(self.a,StudioRecipe(film='monochrome'))
        np.testing.assert_array_equal(mono[:,:,0],mono[:,:,2])
        self.assertFalse(np.array_equal(render(self.a,r),render(self.a,self.r)))

    def test_export_sixteen_bit_preserves_precision_and_profile(self):
        a=render(self.a,self.r)
        data,mime=encode(a,StudioRecipe(file_type='tiff16'))
        with tifffile.TiffFile(BytesIO(data)) as t:
            pixels=t.asarray();self.assertEqual(pixels.dtype,np.uint16)
            self.assertIn(34675,t.pages[0].tags)
            self.assertIn('official-lut-photo-adapter-v1',t.pages[0].description)
        self.assertLess(np.max(abs(pixels/65535-a)),1/65535)
        self.assertEqual(mime,'image/tiff')
        self.assertTrue(np.any(pixels%257))

    def test_adobe_rgb_export_is_color_managed(self):
        if not Path('/System/Library/ColorSync/Profiles/AdobeRGB1998.icc').exists():self.skipTest('macOS profile absent')
        a=render(self.a,self.r)
        data,_=encode(a,StudioRecipe(file_type='tiff8',color_space='adobe_rgb'))
        im=Image.open(BytesIO(data))
        converted=ImageCms.profileToProfile(im,ImageCms.ImageCmsProfile(BytesIO(im.info['icc_profile'])),ImageCms.createProfile('sRGB'),outputMode='RGB')
        self.assertLess(float(np.mean(abs(np.asarray(converted)/255-a))),.012)

    def test_crop_and_invalid_or_unavailable_settings(self):
        out=render(self.a,StudioRecipe(aspect='1:1',digital_crop=2))
        self.assertEqual(out.shape,(48,48,3))
        for change in [{'exposure':float('nan')},{'hdr':'on'},{'file_type':'heif'},{'unknown':1}]:
            with self.subTest(change=change),self.assertRaises(ValidationError):StudioRecipe(**change)
