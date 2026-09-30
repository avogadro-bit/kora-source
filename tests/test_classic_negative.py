import unittest
from kora.official_luts import missing_luts
import numpy as np
from kora.classic_negative import refine_classic_negative
from kora.studio import render, StudioRecipe


def linear_luminance(rgb):
    # Independent sRGB EOTF and CIE Y, used to verify constant luminance even
    # when a saturated colour needs gamut compression.
    linear=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
    return np.sum(linear*np.array([.212671,.715160,.072169]),axis=-1)


class ClassicNegativeTests(unittest.TestCase):
    def test_luminance_and_neutral_axis_are_preserved(self):
        colours=np.random.default_rng(104).uniform(0,1,(90,150,3)).astype(np.float32)
        colours[0,:6]=[[1,0,0],[0,1,0],[0,0,1],[1,1,0],[0,1,1],[1,0,1]]
        actual=refine_classic_negative(colours)
        self.assertTrue(np.isfinite(actual).all())
        self.assertGreaterEqual(actual.min(),0);self.assertLessEqual(actual.max(),1)
        np.testing.assert_allclose(linear_luminance(actual),linear_luminance(colours),atol=6e-7)
        neutral=np.broadcast_to(np.linspace(0,1,1024,dtype=np.float32)[None,:,None],(1,1024,3)).copy()
        np.testing.assert_array_equal(refine_classic_negative(neutral),neutral)

    def test_highlight_and_colour_ramps_have_no_discontinuities(self):
        x=np.linspace(0,1,8192,dtype=np.float32)[None,:,None]
        for end in ([1,.3,.1],[.1,1,.4],[.1,.3,1],[1,.99,.97]):
            a=x*np.array(end,np.float32)
            b=refine_classic_negative(a)
            self.assertLess(abs(np.diff(b,axis=1)).max(),.001)
            np.testing.assert_allclose(linear_luminance(b),linear_luminance(a),atol=6e-7)

    def test_full_frame_and_tile_are_identical(self):
        source=np.random.default_rng(182).uniform(0,1,(300,350,3)).astype(np.float32)
        full=refine_classic_negative(source)
        tile=refine_classic_negative(source[97:247,117:310])
        np.testing.assert_array_equal(tile,full[97:247,117:310])

    @unittest.skipIf(missing_luts(),'Official LUTs unavailable')
    def test_large_tonal_adjustments_remain_bounded_for_all_sources(self):
        source=np.broadcast_to(np.linspace(0,6,1024,dtype=np.float32)[None,:,None],(4,1024,3)).copy()
        source*=np.array([1,.7,.4],np.float32)
        for highlights,whites in ((-100,-100),(-100,100),(100,-100),(100,100)):
            recipe=StudioRecipe(film='classic_negative',highlights=highlights,whites=whites,noise_reduction=-4)
            b=render(source,recipe,context={'source_camera':'X-M5'})
            self.assertTrue(np.isfinite(b).all())
            self.assertGreaterEqual(b.min(),0);self.assertLessEqual(b.max(),1)
            np.testing.assert_array_equal(b,render(source,recipe))
            np.testing.assert_array_equal(b,render(source,recipe,context={'source_camera':'Leica'}))
