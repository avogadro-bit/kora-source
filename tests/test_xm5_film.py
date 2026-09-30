import unittest
from kora.official_luts import missing_luts
import numpy as np
from kora.studio import render, StudioRecipe
from kora.xm5_film import apply_reference_film


class XM5FilmTests(unittest.TestCase):
    @unittest.skipIf(missing_luts(),'Official LUTs unavailable')
    def test_highlight_ramp_stays_finite_bounded_and_continuous(self):
        x=np.linspace(0,8,4096,dtype=np.float32)
        for film in ('pro_neg_hi','nostalgic_negative','classic_negative'):
            for rgb in ([1,1,1],[1,.5,.2],[.1,.7,1]):
                a=x[None,:,None]*np.asarray(rgb,np.float32)
                b=apply_reference_film(a,film)
                self.assertTrue(np.isfinite(b).all())
                self.assertGreaterEqual(b.min(),0);self.assertLessEqual(b.max(),1)
                self.assertLess(abs(np.diff(b,axis=1)).max(),.04)
                if rgb==[1,1,1]:self.assertGreater(np.diff(b.mean(-1)).min(),-.00001)

    @unittest.skipIf(missing_luts(),'Official LUTs unavailable')
    def test_all_sources_use_reference_films_and_tiles_agree(self):
        source=np.random.default_rng(82).uniform(.02,.9,(70,90,3)).astype(np.float32)
        for film in ('pro_neg_hi','nostalgic_negative','classic_negative'):
            recipe=StudioRecipe(film=film,noise_reduction=-4)
            expected=apply_reference_film(source,film)
            for camera in ('X-M5','X100VI','LEICA Q3 43','Canon EOS R6 Mark II','DC-S1R','iXG 100MP',''):
                with self.subTest(film=film,camera=camera):
                    context={'source_camera':camera}
                    actual=render(source,recipe,context=context)
                    np.testing.assert_allclose(actual,expected,atol=1e-7)
                    tile=render(source[13:48,19:57],recipe,context=context,output_transform=False)
                    np.testing.assert_array_equal(tile,actual[13:48,19:57])

    @unittest.skipIf(missing_luts(),'Official LUTs unavailable')
    def test_chrome_and_tone_response_are_shared_after_input_normalization(self):
        source=np.random.default_rng(37).uniform(.01,3,(45,67,3)).astype(np.float32)
        for film in ('classic_negative','nostalgic_negative','pro_neg_hi','provia'):
            recipe=StudioRecipe(film=film,noise_reduction=-4,highlights=-63.5,
                                whites=-47.2,color_chrome='strong',fx_blue='weak')
            expected=render(source,recipe,context={'source_camera':'X-M5'})
            for camera in ('LEICA Q3 43','Canon EOS R6 Mark II','X100VI',''):
                np.testing.assert_array_equal(render(source,recipe,context={'source_camera':camera}),expected)

    def test_neutral_view_bypasses_reference_films_and_effects(self):
        source=np.random.default_rng(6).uniform(.01,.9,(35,57,3)).astype(np.float32)
        baseline=render(source,StudioRecipe(noise_reduction=-4),neutral=True)
        for film in ('classic_negative','nostalgic_negative','pro_neg_hi'):
            recipe=StudioRecipe(film=film,noise_reduction=-4,color_chrome='strong')
            np.testing.assert_array_equal(render(source,recipe,neutral=True),baseline)
