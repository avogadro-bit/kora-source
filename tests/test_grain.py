import unittest
from unittest.mock import patch
import numpy as np
from kora.grain import film_grain, apply_film_grain, _small_grain
from kora.studio import render, StudioRecipe


class GrainTests(unittest.TestCase):
    def test_exposure_fit_reuses_grain_without_reusing_scene_pixels(self):
        _small_grain.cache_clear()
        source=np.random.default_rng(12).uniform(.02,.9,(40,60,3)).astype(np.float32)
        outputs=[]
        with patch('kora.grain.film_grain',wraps=film_grain) as field:
            for strength,exposure in [('weak',.5),('strong',1),('weak',1.5)]:
                pixels=source*exposure
                apply_film_grain(pixels,strength,'large',.25,(13,17))
                outputs.append(pixels)
            field.assert_called_once()
            cached=_small_grain((40,60),'large',.25,(13,17))
            self.assertFalse(cached.flags.writeable)
            # Origin, scale, and grain size must remain part of the key.
            for size,scale,origin in [('small',.25,(13,17)),('large',.5,(13,17)),('large',.25,(14,17))]:
                apply_film_grain(source.copy(),'weak',size,scale,origin)
            self.assertEqual(field.call_count,4)
        # Compare against the uncached grain field on every exposure/strength.
        with patch('kora.grain._small_grain',side_effect=film_grain):
            for (strength,exposure),actual in zip([('weak',.5),('strong',1),('weak',1.5)],outputs):
                expected=source*exposure
                apply_film_grain(expected,strength,'large',.25,(13,17))
                np.testing.assert_array_equal(actual,expected)
        with patch('kora.grain._small_grain') as cached:
            apply_film_grain(np.full((260,270,3),.5,np.float32),'weak','small')
            cached.assert_not_called()
        _small_grain.cache_clear()

    def test_strength_and_size_are_distinct_and_repeatable(self):
        for size in ('small','large'):
            weak=np.full((512,512,3),.5,np.float32)
            strong=weak.copy();repeat=weak.copy()
            apply_film_grain(weak,'weak',size)
            apply_film_grain(strong,'strong',size)
            apply_film_grain(repeat,'strong',size)
            np.testing.assert_array_equal(strong,repeat)
            self.assertGreater(strong.std(),1.8*weak.std())
        def adjacent(a):return np.corrcoef(a[:,:-1].flat,a[:,1:].flat)[0,1]
        small=film_grain((512,512),'small')
        large=film_grain((512,512),'large')
        self.assertLess(adjacent(small),.3)
        self.assertGreater(adjacent(large),adjacent(small)+.2)
        self.assertAlmostEqual(float(small.std()/large.std()),1,delta=.05)

    def test_measured_xm5_midtones_at_camera_output_scale(self):
        # Held-out camera pairs: SMALL weak .028-.034 / strong .057-.072;
        # LARGE weak .014-.016 / strong .029-.035, with much longer clusters.
        for size,bounds,corr_bounds in [('small',(.025,.037),(.12,.30)),
                                       ('large',(.012,.018),(.62,.80))]:
            a=np.full((512,768,3),.5,np.float32)
            apply_film_grain(a,'weak',size,6240/6000)
            noise=a[...,0]-.5
            self.assertGreater(noise.std(),bounds[0]);self.assertLess(noise.std(),bounds[1])
            corr=np.corrcoef(noise[:,:-1].flat,noise[:,1:].flat)[0,1]
            self.assertGreater(corr,corr_bounds[0]);self.assertLess(corr,corr_bounds[1])

    def test_tiles_have_no_boundary_seams_at_fractional_scale(self):
        for scale in (1.,1.5893,.25):
            for size in ('small','large'):
                full=film_grain((390,430),size,scale)
                tile=film_grain((170,199),size,scale,(127,203))
                np.testing.assert_array_equal(tile,full[127:297,203:402])

    def test_reduced_views_retain_the_pattern_and_attenuate_grain(self):
        for size in ('small','large'):
            full=film_grain((512,512),size)
            for factor in (2,4):
                small=film_grain((512//factor,512//factor),size,1/factor)
                average=full.reshape(512//factor,factor,512//factor,factor).mean((1,3))
                self.assertGreater(np.corrcoef(small.flat,average.flat)[0,1],.9)
                self.assertLess(small.std(),full.std()*.9)
                self.assertAlmostEqual(float(small.std()/average.std()),1,delta=.3)

    def test_no_black_haze_white_speckles_or_coloured_noise(self):
        deviations=[]
        for level in (0,.01,.5,.99,1):
            a=np.full((384,384,3),level,np.float32)
            apply_film_grain(a,'strong','large')
            np.testing.assert_array_equal(a[...,0],a[...,1])
            np.testing.assert_array_equal(a[...,0],a[...,2])
            self.assertGreaterEqual(a.min(),0);self.assertLessEqual(a.max(),1)
            self.assertLess(abs(float(a.mean()-level)),.003)
            deviations.append(a.std())
        self.assertEqual(deviations[0],0);self.assertEqual(deviations[-1],0)
        self.assertLess(deviations[1],deviations[2]*.1)
        self.assertLess(deviations[-2],deviations[2]*.1)

    def test_saturated_colours_stay_in_gamut_with_stable_hue_direction(self):
        a=np.broadcast_to(np.array([.99,.5,.01],np.float32),(256,256,3)).copy()
        before=a.copy();apply_film_grain(a,'strong','small')
        w=np.array([.2126,.7152,.0722],np.float32)
        c=before-np.sum(before*w,-1,keepdims=True)
        d=a-np.sum(a*w,-1,keepdims=True)
        self.assertLess(abs(np.cross(c,d)).max(),1e-6)
        self.assertGreaterEqual(a.min(),0);self.assertLessEqual(a.max(),1)

    def test_rendered_grain_matches_full_frame_when_viewed_as_tiles(self):
        source=np.full((400,450,3),.25,np.float32)
        recipe=StudioRecipe(film='monochrome',noise_reduction=-4,grain='strong')
        full=render(source,recipe,context={'full_shape':(6000,6000,3)})
        tile=render(source[127:297,203:402],recipe,output_transform=False,
                    context={'full_shape':(6000,6000,3)},origin=(127,203))
        np.testing.assert_array_equal(tile,full[127:297,203:402])
