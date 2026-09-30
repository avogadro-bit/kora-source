from kora.official_luts import missing_luts
import unittest
from unittest.mock import patch
import numpy as np
from scipy.ndimage import uniform_filter
from kora.recipe_effects import wb_shift_gains, chrome_effect, dynamic_range_compress, tone_curve, linear_tone_curve, selective_tone_detail
from kora.studio import render, StudioRecipe


class RecipeEffectTests(unittest.TestCase):
    def test_tone_curve_monotonic_and_independent_across_all_half_steps(self):
        a=np.repeat(np.linspace(0,1,2001,dtype=np.float32)[None,:,None],3,-1)
        for key in ('highlights','shadows'):
            previous=None
            for setting in np.arange(-2,4.1,.5):
                out=tone_curve(a,**{key:setting})
                self.assertTrue(np.all(np.diff(out,axis=1)>=0))
                np.testing.assert_allclose(out[:,[0,1000,2000]],a[:,[0,1000,2000]],atol=1e-6)
                protected=slice(None,1001) if key=='highlights' else slice(1000,None)
                np.testing.assert_allclose(out[:,protected],a[:,protected],atol=1e-6)
                if previous is not None:
                    delta=out-previous
                    self.assertTrue(np.all(delta>=-1e-6) if key=='highlights' else np.all(delta<=1e-6))
                previous=out

    def test_tone_controls_have_visible_strength_and_default_is_unchanged(self):
        a=np.array([[[.25]*3,[.75]*3]],np.float32)
        self.assertIs(tone_curve(a),a)
        self.assertLess(tone_curve(a,shadows=4)[0,0,0],.1)
        self.assertGreater(tone_curve(a,shadows=-2)[0,0,0],.34)
        self.assertGreater(tone_curve(a,highlights=4)[0,1,0],.9)
        self.assertLess(tone_curve(a,highlights=-2)[0,1,0],.66)

    def test_wb_recovered_q10_reference_and_asymmetric_extremes(self):
        np.testing.assert_array_equal(wb_shift_gains(0,0),[1,1,1])
        np.testing.assert_allclose(wb_shift_gains(9,-9),[1896/1024,1,587/1024])
        reds=[wb_shift_gains(i,0)[0] for i in range(-9,10)]
        self.assertTrue(np.all(np.diff(reds)>0))
        self.assertGreater(reds[-1],1.8)
        self.assertLess(reds[0],.55)

    def test_chrome_preserves_gray_and_fx_blue_excludes_warm_colors(self):
        gray=np.repeat(np.linspace(0,1,20,dtype=np.float32)[None,:,None],3,axis=-1)
        for blue in [False,True]:np.testing.assert_allclose(chrome_effect(gray,'strong',blue),gray)
        warm=np.array([[[.8,.4,.1],[.2,.7,.1],[.7,.7,.2]]],np.float32)
        np.testing.assert_array_equal(chrome_effect(warm,'strong',True),warm)
        sky=np.array([[[.3,.5,.8]]],np.float32)
        weak=chrome_effect(sky,'weak',True);strong=chrome_effect(sky,'strong',True)
        self.assertTrue(np.all(strong<weak));self.assertTrue(np.all(weak<sky))
        np.testing.assert_allclose(strong[...,2]-strong[...,0],sky[...,2]-sky[...,0],atol=1e-6)

    def test_dynamic_range_retains_midtones_and_increasing_highlight_compression(self):
        a=np.repeat(np.array([[[.01],[.18],[.8],[2.]]],np.float32),3,axis=-1)
        dr200=dynamic_range_compress(a,200);dr400=dynamic_range_compress(a,400)
        np.testing.assert_allclose(dr200[:,:2],a[:,:2],atol=1e-6)
        self.assertTrue(np.all(dr400[:,2:]<dr200[:,2:]))
        self.assertTrue(np.all(dr200[:,2:]<a[:,2:]))

    def test_dynamic_range_maps_one_and_two_extra_stops_to_white(self):
        for level in (200,400):
            ramp=np.repeat(np.linspace(0,level/100,2001,dtype=np.float32)[None,:,None],3,-1)
            result=dynamic_range_compress(ramp,level)
            np.testing.assert_allclose(result[:,-1],1,atol=1e-6)
            self.assertTrue(np.all(np.diff(result,axis=1)>0))

    def test_dynamic_range_never_inverts_signed_out_of_gamut_pixels(self):
        signed=np.array([[[-.12,-.04,-.08],[-.1,.01,.02],[.8,.9,1.1]]],np.float32)
        for level in (200,400):
            result=dynamic_range_compress(signed,level)
            self.assertTrue(np.isfinite(result).all())
            np.testing.assert_array_equal(result[:,:2],signed[:,:2])
            self.assertLessEqual(float(result.max()),1.1)

    def test_chrome_does_not_exaggerate_saturated_red_or_clip_channels(self):
        a=np.array([[[.9,.15,.04],[.9,.02,0],[0,.9,0]]],np.float32)
        strong=chrome_effect(a,'strong')
        self.assertTrue(np.all(strong.max(-1)<a.max(-1)))
        self.assertTrue(np.all(strong[0,0]>0))
        np.testing.assert_allclose(chrome_effect(a,'weak'),(a+strong)/2,atol=1e-7)

    @unittest.skipIf(missing_luts(), "Official LUT integration: install Fuji assets separately")
    def test_priority_overrides_manual_dr_and_tone(self):
        a=np.random.default_rng(9).uniform(0,.9,(24,32,3)).astype(np.float32)
        r=StudioRecipe(dr_priority='weak')
        np.testing.assert_array_equal(render(a,r),render(a,r.model_copy(update={
            'shadows':-100,'blacks':100,'highlights':100,'whites':-100,
            'dynamic_range':400})))

    @unittest.skipIf(missing_luts(), "Official LUT integration: install Fuji assets separately")
    def test_spatial_controls_affect_details_in_expected_direction(self):
        rng=np.random.default_rng(8);a=rng.uniform(.1,.5,(96,96,3)).astype(np.float32)
        baseline=render(a,StudioRecipe())
        highpass=lambda x:float(np.mean(abs(np.diff(x,axis=1))))
        self.assertLess(highpass(render(a,StudioRecipe(noise_reduction=4))),highpass(baseline))
        self.assertGreater(highpass(render(a,StudioRecipe(sharpness=4))),highpass(baseline))
        self.assertLess(highpass(render(a,StudioRecipe(sharpness=-4))),highpass(baseline))

    def test_linear_tones_keep_hdr_gradation_and_channel_ratios(self):
        a=np.repeat(np.geomspace(.0001,16,500,dtype=np.float32)[None,:,None],3,-1)
        for settings in [dict(highlights=-100),dict(shadows=100),
                         dict(whites=-100),dict(blacks=100),
                         dict(highlights=100,whites=100,shadows=-100,blacks=-100)]:
            out=linear_tone_curve(a,**settings)
            self.assertTrue(np.all(np.diff(out,axis=1)>0))
            self.assertTrue(np.isfinite(out).all())
        rgb=np.array([[[2.,1.,.5]]],np.float32)
        out=linear_tone_curve(rgb,highlights=-100)
        np.testing.assert_allclose(out/rgb,(out/rgb)[...,0:1].repeat(3,-1),rtol=1e-6)
        np.testing.assert_array_equal(linear_tone_curve(np.zeros_like(rgb),-100,100,-100,100),0)

    def test_four_way_tones_target_distinct_luminance_zones(self):
        levels=np.array([.005,.02,.08,.18,.55,.9,2.4],np.float32)
        a=np.repeat(levels[None,:,None],3,-1)
        blacks=linear_tone_curve(a,blacks=100)[0,:,0]
        shadows=linear_tone_curve(a,shadows=100)[0,:,0]
        highlights=linear_tone_curve(a,highlights=-100)[0,:,0]
        whites=linear_tone_curve(a,whites=-100)[0,:,0]
        self.assertGreater(blacks[0],levels[0]);np.testing.assert_allclose(blacks[2:],levels[2:],rtol=1e-6)
        self.assertGreater(shadows[2],levels[2]);np.testing.assert_allclose(shadows[3:],levels[3:],rtol=1e-6)
        np.testing.assert_allclose(highlights[:4],levels[:4],rtol=1e-6);self.assertLess(highlights[4],levels[4])
        np.testing.assert_allclose(whites[:5],levels[:5],rtol=1e-6)
        self.assertLess(whites[5],levels[5]);self.assertLess(whites[6],levels[6])

    def test_tones_recover_before_film_clipping_not_after(self):
        a=np.repeat(np.array([[[1.2],[1.5],[2.]]],np.float32),3,-1)
        # A clipping film makes a display-space edit incapable of distinguishing
        # these three inputs. A pre-film highlight edit must retain their detail.
        with patch('kora.studio.apply_official',side_effect=lambda a,film:np.clip(a,0,1)):
            old=render(a,StudioRecipe())
            recovered=render(a,StudioRecipe(highlights=-100,dynamic_range=400))
        np.testing.assert_array_equal(old,1)
        self.assertTrue(np.all(np.diff(recovered,axis=1)>0))
        self.assertTrue(np.all(recovered<1))

    def test_tone_detail_preserves_cloud_gradients_and_restores_shadow_texture(self):
        y,x=np.mgrid[:320,:480]
        cloud=.75+.18*np.sin(x/13)*np.sin(y/17)
        cloud+=.12*np.exp(-((x-250)**2+(y-130)**2)/(2*85**2))
        source=np.repeat(cloud[...,None].astype(np.float32),3,-1)
        compressed=linear_tone_curve(source,highlights=-100)
        recovered=selective_tone_detail(source,compressed,highlights=-100)
        highpass=lambda a:a[:,:,0]-uniform_filter(a[:,:,0],size=31,mode='reflect')
        # Highlight reduction must not acquire local white rims/dark lobes.
        np.testing.assert_array_equal(recovered,compressed)
        np.testing.assert_array_equal(
            selective_tone_detail(source,compressed,highlights=-100,shadows=100,blacks=100),
            compressed)
        flat=np.full((160,240,3),.8,np.float32)
        flat_compressed=linear_tone_curve(flat,highlights=-100)
        np.testing.assert_allclose(selective_tone_detail(flat,flat_compressed,highlights=-100),
                                   flat_compressed,atol=2e-5)
        shadow=np.repeat((.09+.045*np.sin(x/11)*np.sin(y/15))[...,None].astype(np.float32),3,-1)
        lifted=linear_tone_curve(shadow,shadows=100)
        shadow_recovered=selective_tone_detail(shadow,lifted,shadows=100)
        self.assertGreater(float(highpass(shadow_recovered).std()),
                           1.05*float(highpass(lifted).std()))
        self.assertTrue(np.isfinite(recovered).all())

    def test_old_dng_context_cannot_cancel_highlight_recovery(self):
        source=np.repeat(np.linspace(1,3,32,dtype=np.float32)[None,:,None],3,-1)
        recipe=StudioRecipe(highlights=-100,noise_reduction=-4)
        with patch('kora.studio.apply_official',side_effect=lambda a,film:np.clip(a,0,1)):
            ordinary=render(source,recipe)
            protected=render(source,recipe,context={'protect_neutral_clipped_highlights':True})
        np.testing.assert_array_equal(protected,ordinary)
        self.assertTrue(np.all(np.diff(protected[0,:,0])>0))

    @unittest.skipIf(missing_luts(), "Official LUT integration: install Fuji assets separately")
    def test_tone_adjustments_keep_official_film_hue_and_raw_luminance(self):
        from kora.official_luts import FILMS
        weights=np.array([.2126,.7152,.0722],np.float32)
        raw=np.random.default_rng(55).uniform(.02,3,(12,16,3)).astype(np.float32)
        for film in FILMS:
            base=render(raw,StudioRecipe(film=film))
            base_c=base-np.sum(base*weights,-1)[...,None]
            for change in ({'highlights':-100},{'whites':-100},{'shadows':100},
                           {'blacks':100},{'dynamic_range':400}):
                edited=render(raw,StudioRecipe(film=film,**change))
                c=edited-np.sum(edited*weights,-1)[...,None]
                # Hue direction in the RGB chroma plane must not rotate.
                cross=np.cross(base_c,c)
                reliable=base.max(-1)<=.85
                self.assertLess(float(np.abs(cross[reliable]).max(initial=0)),2e-6)
                self.assertTrue(np.all(np.sum(base_c*c,-1)[reliable]>=-1e-7))

    def test_color_stabilization_keeps_recovered_color_at_clipped_film_white(self):
        from kora.recipe_effects import preserve_film_hue
        base=np.ones((1,3,3),np.float32)
        magenta=np.array([[[.9,.4,.8],[.8,.3,.7],[.7,.2,.6]]],np.float32)
        out=preserve_film_hue(base,magenta)
        np.testing.assert_allclose(out,magenta,atol=1e-7)
        self.assertTrue(np.all(np.diff(out,axis=1)<0))
        weights=np.array([.2126,.7152,.0722],np.float32)
        np.testing.assert_allclose(np.sum(out*weights,-1),np.sum(magenta*weights,-1),atol=1e-7)

    def test_recovered_color_blend_is_continuous_and_preserves_luminance(self):
        from kora.recipe_effects import preserve_film_hue
        levels=np.linspace(.84,1,1601,dtype=np.float32)[None,:,None]
        base=np.repeat(levels,3,-1)
        adjusted=np.broadcast_to(np.array([.8,.6,.4],np.float32),base.shape)
        out=preserve_film_hue(base,adjusted)
        weights=np.array([.2126,.7152,.0722],np.float32)
        np.testing.assert_allclose(np.sum(out*weights,-1),np.sum(adjusted*weights,-1),atol=2e-7)
        self.assertLess(np.abs(np.diff(out,axis=1)).max(),.001)
        gray=np.repeat(levels*.8,3,-1)
        np.testing.assert_allclose(preserve_film_hue(base,gray),gray,atol=2e-7)

    def test_whites_still_work_after_maximum_highlight_reduction(self):
        source=np.full((8,16,3),2.,np.float32)
        highlights=linear_tone_curve(source,highlights=-100)
        both=linear_tone_curve(source,highlights=-100,whites=-100)
        self.assertLess(float(both.mean()),float(highlights.mean())*.9)

    def test_highlight_controls_have_fine_steps_and_extended_latitude(self):
        source=np.repeat(np.array([.08,.18,1.,2.,4.,8.,16.],np.float32)[None,:,None],3,-1)
        for key in ('highlights','whites'):
            previous=None
            for value in (0,-.1,-.2,-1,-10,-25,-50,-75,-100):
                out=linear_tone_curve(source,**{key:value})
                np.testing.assert_allclose(out[:,:2],source[:,:2],atol=1e-7)
                if previous is not None:self.assertTrue(np.all(out[:,2:]<previous[:,2:]))
                if value==-.1:self.assertLess(float(np.max(np.abs(out/source-1))),.003)
                previous=out
        recovered=linear_tone_curve(source,highlights=-100,whites=-100)
        # Three stops of reduction at the far end, with contrast left in the
        # bright tail. Requiring 16 -> .55 encoded the old flat grey plateau.
        self.assertLess(float(recovered[0,-1,0]),2.1)
        self.assertLess(float(recovered[0,4,0]),.7)
        self.assertTrue(np.all(np.diff(recovered[0,:,0])>0))

    def test_maximum_recovery_retains_broad_highlight_gradients(self):
        ev=np.linspace(0,9,4097,dtype=np.float32)
        source=np.repeat((.18*np.exp2(ev))[None,:,None],3,-1)
        out=linear_tone_curve(source,highlights=-100,whites=-100)
        contrast=np.diff(np.log2(out[0,:,0]))/np.diff(ev)
        # The old curve retained only 1/16 contrast, even across broad skies
        # where a fine-detail filter cannot help. Keep tonal order and a
        # useful contrast floor; resume ordinary exposure contrast above it.
        self.assertGreater(float(contrast.min()),.17)
        np.testing.assert_allclose(contrast[ev[1:]>6],1,atol=.002)

    def test_opposite_highlight_controls_cannot_reverse_tonal_order(self):
        source=np.repeat(np.geomspace(.001,64,4096,dtype=np.float32)[None,:,None],3,-1)
        for highlights in (-100,-50,0,50,100):
            for whites in (-100,-50,0,50,100):
                out=linear_tone_curve(source,highlights=highlights,whites=whites)
                self.assertTrue(np.all(np.diff(out[0,:,0])>0),(highlights,whites))

    def test_highlight_base_compression_retains_fine_raw_texture(self):
        x=np.arange(512,dtype=np.float32)
        light=2*np.exp2(.025*np.sin(x*1.3))
        source=np.broadcast_to(light[None,:,None],(80,512,3)).copy()
        point=linear_tone_curve(source,-100,whites=-100)
        detail=linear_tone_curve(source,-100,whites=-100,detail_scale=1)
        contrast=lambda a:float(np.std(np.log2(a[40,32:-32,0])))
        self.assertGreater(contrast(detail),.8*contrast(source))
        self.assertGreater(contrast(detail),4*contrast(point))
        # A strong edge must not become a bright or dark rim.
        source[:,:256]=.08;source[:,256:]=4
        point=linear_tone_curve(source,-100,whites=-100)
        detail=linear_tone_curve(source,-100,whites=-100,detail_scale=1)
        np.testing.assert_allclose(detail[:,:256],source[:,:256],atol=1e-6)
        self.assertLess(float(np.max(np.abs(detail[:,256:]/point[:,256:]-1))),.01)

    def test_highlight_detail_full_and_halo_tile_match(self):
        source=np.random.default_rng(411).uniform(.02,4,(360,640,3)).astype(np.float32)
        full=linear_tone_curve(source,-75,whites=-50,detail_scale=2)
        tile=linear_tone_curve(source[32:328,64:576],-75,whites=-50,detail_scale=2)
        np.testing.assert_allclose(tile[96:-96,96:-96],full[128:232,160:480],atol=2e-6)

    def test_fractional_tones_survive_recipe_round_trip(self):
        from pydantic import ValidationError
        recipe=StudioRecipe(highlights=-37.6,whites=12.3)
        restored=StudioRecipe.model_validate_json(recipe.model_dump_json())
        self.assertEqual(restored.highlights,-37.6)
        self.assertEqual(restored.whites,12.3)
        for value in (-100.1,100.1,float('nan'),float('inf')):
            with self.assertRaises(ValidationError):StudioRecipe(highlights=value)
