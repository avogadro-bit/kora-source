from kora.official_luts import missing_luts
import unittest
from unittest.mock import patch
import numpy as np
from kora.official_luts import (
    FILMS, TO_F_GAMUT, flog2_encode, load_lut, interpolate, apply_official,
    lut_worker_count)
from kora.studio import StudioRecipe, render
from kora.classic_negative import refine_classic_negative


class OfficialLutTests(unittest.TestCase):
    def test_lut_worker_count_uses_cpu_without_oversubscription(self):
        self.assertEqual(lut_worker_count(1),1)
        self.assertEqual(lut_worker_count(4),3)
        self.assertEqual(lut_worker_count(64),10)

    def test_fuji_gamma22_viewing_converts_to_browser_srgb(self):
        # A 50% gamma-2.2 video code is ~50.39% in sRGB. The previous
        # gamma-2.4 assumption instead produced ~47.25%, a visible error.
        codes=np.array([[[0,.5,1]]],np.float32)
        with patch('kora.official_luts.load_lut',return_value=None), patch('kora.official_luts.interpolate',return_value=codes):
            out=apply_official(np.zeros_like(codes),'classic_negative')
        np.testing.assert_allclose(out,[[[0,.503866782,1]]],atol=1e-6)

    def test_flog2_matches_manufacturer_reference_codes(self):
        np.testing.assert_allclose(flog2_encode(np.array([0,.18,.9]))*1023,
                                   [95,400,570],atol=1)
        np.testing.assert_allclose(np.ones(3)@TO_F_GAMUT,1,atol=1e-6)

    def test_cube_axis_order_endpoints_and_interpolation(self):
        b,g,r=np.meshgrid(*([np.linspace(0,1,65,dtype=np.float32)]*3),indexing='ij')
        table=np.stack([r,g,b],axis=-1)
        samples=np.array([[[0,0,0],[1,1,1],[.1,.3,.7],[1,0,0]]],np.float32)
        np.testing.assert_allclose(interpolate(table,samples),samples,atol=1e-6)

    @unittest.skipIf(missing_luts(), "Official LUT integration: install Fuji assets separately")
    def test_all_ten_verified_tables_render_with_declared_photo_adaptation(self):
        self.assertEqual(len(FILMS),10)
        a=np.random.default_rng(15).uniform(0,1,(24,32,3)).astype(np.float32)
        for film in FILMS:
            with self.subTest(film=film):
                self.assertEqual(load_lut(film).shape,(65,65,65,3))
                output=render(a,StudioRecipe(film=film))
                expected=apply_official(a,film)
                if film=='classic_negative':expected=refine_classic_negative(expected)
                np.testing.assert_allclose(output,expected,atol=2e-6)
                self.assertTrue(np.isfinite(output).all())
                self.assertTrue(((output>=0)&(output<=1)).all())
        self.assertGreater(float(abs(apply_official(a,'provia')-apply_official(a,'classic_negative')).mean()),.02)

    @unittest.skipIf(missing_luts(), "Official LUT integration: install Fuji assets separately")
    def test_exposure_above_one_reaches_lut_before_display_clipping(self):
        a=np.full((2,2,3),.8,np.float32)
        actual=render(a,StudioRecipe(film='classic_negative',exposure=1))
        expected=refine_classic_negative(apply_official(a*2,'classic_negative'))
        clipped=refine_classic_negative(apply_official(np.clip(a*2,0,1),'classic_negative'))
        np.testing.assert_allclose(actual,expected,atol=1e-6)
        self.assertGreater(float(abs(actual-clipped).max()),.001)

    @unittest.skipIf(missing_luts(), "Official LUT integration: install Fuji assets separately")
    def test_parallel_lut_is_identical_to_single_thread(self):
        a=np.random.default_rng(91).uniform(0,2,(512,32,3)).astype(np.float32)
        np.testing.assert_array_equal(apply_official(a,'provia',workers=1),
                                      apply_official(a,'provia',workers=4))

    @unittest.skipIf(missing_luts(), "Official LUT integration: install Fuji assets separately")
    def test_acros_filter_is_applied_before_monochrome_conversion(self):
        a=np.array([[[.5,.1,.02],[.02,.1,.5]]],np.float32)
        plain=render(a,StudioRecipe(film='acros'))
        filtered=render(a,StudioRecipe(film='acros',mono_filter='red'))
        self.assertGreater(float(abs(plain-filtered).mean()),.01)
