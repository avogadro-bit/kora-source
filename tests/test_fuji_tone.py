import unittest
import numpy as np
from pydantic import ValidationError
from kora.fuji_tone import apply_fuji_tone, tone_curve
from kora.studio import StudioRecipe, render, shooting_settings
from kora.official_luts import missing_luts


class FujiToneTests(unittest.TestCase):
    def test_native_range_and_half_steps_are_validated(self):
        for value in np.arange(-2, 4.1, .5):
            r=StudioRecipe(highlight_tone=value,shadow_tone=value)
            self.assertEqual(StudioRecipe.model_validate_json(r.model_dump_json()),r)
        for value in [-2.5,4.5,.1,float('nan'),float('inf')]:
            for key in ('highlight_tone','shadow_tone'):
                with self.assertRaises(ValidationError):StudioRecipe(**{key:value})

    def test_old_recipes_keep_their_four_way_values_and_zero_new_effect(self):
        r=StudioRecipe(version=2,highlights=-72.3,whites=-18.1,shadows=32,blacks=-5)
        self.assertEqual((r.highlights,r.whites,r.shadows,r.blacks),(-72.3,-18.1,32,-5))
        self.assertEqual((r.highlight_tone,r.shadow_tone),(0,0))
        old=StudioRecipe(version=1,highlights=-2,shadows=2)
        self.assertEqual((old.highlights,old.shadows),(-50,-50))
        self.assertEqual((old.highlight_tone,old.shadow_tone),(0,0))

    def test_capture_import_retains_half_steps_without_double_tone(self):
        r=StudioRecipe(**shooting_settings({'HighlightTone':'-1.5','ShadowTone':'+0.5'}))
        self.assertEqual((r.highlight_tone,r.shadow_tone),(-1.5,.5))
        self.assertEqual((r.highlights,r.whites,r.shadows,r.blacks),(0,0,0,0))
        legacy=StudioRecipe(**shooting_settings({'HighlightTone':'-2','ShadowTone':'+1'},legacy_tone=True))
        self.assertEqual((legacy.highlights,legacy.shadows),(-50,-25))
        self.assertEqual((legacy.highlight_tone,legacy.shadow_tone),(0,0))

    def test_zero_is_exact_identity_and_nonzero_does_not_modify_source(self):
        a=np.random.default_rng(31).random((32,41,3),dtype=np.float32)
        original=a.copy();self.assertIs(apply_fuji_tone(a),a)
        apply_fuji_tone(a,-2,4)
        np.testing.assert_array_equal(a,original)

    def test_every_joint_setting_has_monotone_finite_tones_and_neutral_greys(self):
        ramp=np.repeat(np.linspace(0,1,4097,dtype=np.float32)[None,:,None],3,-1)
        for h in np.arange(-2,4.1,.5):
            for s in np.arange(-2,4.1,.5):
                curve=tone_curve(float(h),float(s))
                self.assertGreaterEqual(float(np.diff(curve).min()),-1e-7)
                b=apply_fuji_tone(ramp,h,s)
                self.assertTrue(np.isfinite(b).all())
                self.assertGreaterEqual(float(b.min()),0);self.assertLessEqual(float(b.max()),1)
                self.assertGreaterEqual(float(np.diff(b[0,:,0]).min()),-1e-7)
                np.testing.assert_allclose(b[:,:,0],b[:,:,1],atol=1e-7)
                np.testing.assert_allclose(b[:,:,1],b[:,:,2],atol=1e-7)
                np.testing.assert_allclose(b[0,[0,-1],0],[0,1],atol=1e-6)

    def test_native_sign_and_region_are_distinct(self):
        axis=np.linspace(0,1,4097)
        h=tone_curve(4,0)-axis;s=tone_curve(0,4)-axis
        self.assertGreater(h[3072],.05);self.assertLess(abs(h[1024]),.003)
        self.assertLess(s[1024],-.07);self.assertLess(abs(s[3072]),.003)
        for i in range(12):
            low=-2+i*.5;high=low+.5
            self.assertGreaterEqual(float(np.min(tone_curve(high,0)-tone_curve(low,0))),-2e-5)
            self.assertLessEqual(float(np.max(tone_curve(0,high)-tone_curve(0,low))),2e-5)

    def test_tile_and_full_match_for_saturated_colours(self):
        a=np.random.default_rng(32).random((270,150,3),dtype=np.float32)
        a[0,:3]=[[1,0,0],[0,1,0],[0,0,1]]
        b=apply_fuji_tone(a,4,-2)
        self.assertTrue(np.isfinite(b).all())
        self.assertTrue((b>=0).all() and (b<=1).all())
        np.testing.assert_array_equal(b[17:173,23:121],apply_fuji_tone(a[17:173,23:121],4,-2))

    @unittest.skipIf(missing_luts(),'Official LUTs unavailable')
    def test_shared_pipeline_and_priority_takeover(self):
        a=np.random.default_rng(33).random((30,41,3),dtype=np.float32)*.8
        for film in ('classic_negative','provia','astia','acros'):
            r=StudioRecipe(film=film,highlight_tone=-2,shadow_tone=4)
            b=render(a,r)
            np.testing.assert_array_equal(b,render(a,r,context={'camera_model':'LEICA Q3 43'}))
            self.assertGreater(float(abs(b-render(a,StudioRecipe(film=film))).mean()),.001)
            r=StudioRecipe(film=film,dr_priority='weak',highlight_tone=-2,shadow_tone=4)
            np.testing.assert_array_equal(render(a,r),render(a,r.model_copy(update={'highlight_tone':0,'shadow_tone':0})))
