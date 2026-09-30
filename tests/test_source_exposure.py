import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import numpy as np
from kora.source_exposure import source_exposure, estimate_reference_ev
from kora.studio import decode, _preview_source, _decode_sensor


class SourceExposureTests(unittest.TestCase):
    def test_q3_reference_color_applies_once_to_preview_and_full_decode(self):
        metadata={'Make':'LEICA CAMERA AG','Model':'LEICA Q3 43','BaselineExposure':.25}
        pixels=np.array([[[-.1,.2,2.],[.5,.8,.3]]],np.float32)
        _preview_source.cache_clear()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'fixture.dng';path.write_bytes(b'fixture')
            with patch('kora.studio.exif',return_value=metadata), \
                 patch('kora.studio._decode_sensor',side_effect=lambda *a,**kw:(pixels.copy(),None)):
                preview=decode(path,preview=True);full=decode(path,preview=False)
        expected=pixels*2**.25*np.array([1.0018982841,1.,.9798716044],np.float32)
        np.testing.assert_allclose(preview,expected,atol=1e-7)
        np.testing.assert_array_equal(preview,full)
        _preview_source.cache_clear()

    def test_leica_float_input_uses_dng_baseline_and_preview_estimation(self):
        metadata={'Make':'LEICA CAMERA AG','Model':'LEICA M11','BaselineExposure':.25}
        profile=source_exposure(metadata,'.DNG')
        self.assertAlmostEqual(profile['ev'],.25)
        self.assertTrue(profile['floating_camera_rgb'])
        self.assertNotIn('fixed_camera_exposure',profile)
        _preview_source.cache_clear();a=np.full((3,4,3),.2,np.float32)
        with patch('kora.studio.exif',return_value=metadata), \
             patch('kora.studio._decode_sensor',return_value=(a,np.full_like(a,.3))) as decoder, \
             patch('kora.studio.estimate_reference_ev',return_value={'reference_ev':.5,'reference_matched':True}) as estimate:
            pixels,info=_preview_source(Path('leica.DNG'),0,0)
            estimate.assert_called_once()
            self.assertTrue(decoder.call_args.kwargs['floating_camera_rgb'])
            np.testing.assert_allclose(pixels,.2*2**.75)
            self.assertEqual(info['metadata_ev'],.25)
        _preview_source.cache_clear()

    def test_leica_float_matrix_preserves_signed_colours_and_headroom(self):
        raw=MagicMock();raw.__enter__.return_value=raw
        raw.white_level=16383;raw.black_level_per_channel=[512]*4
        raw.postprocess.return_value=np.array([[[20000,1000,1000]]],np.uint16)
        raw.color_matrix=np.array([[1,0,0,0],[-.2,1.2,0,0],[0,0,1,0]],np.float32)
        raw.raw_image_visible=np.full((2,2),1000,np.uint16)
        raw.raw_pattern=np.array([[0,1],[3,2]])
        raw.sizes.flip=0
        raw.extract_thumb.side_effect=OSError('no thumbnail')
        with tempfile.TemporaryDirectory() as tmp,patch('kora.studio.rawpy.imread',return_value=raw):
            path=Path(tmp)/'leica.dng';path.write_bytes(b'fixture')
            preview,_=_decode_sensor(path,True,True)
            full,_=_decode_sensor(path,False,True)
            self.assertLess(float(preview.min()),0)
            self.assertGreater(float(preview.max()),1)
            np.testing.assert_array_equal(preview,full)
            raw.raw_image_visible[:]=16383
            clipped,_=_decode_sensor(path,True,True)
            np.testing.assert_allclose(clipped[:,:,0],clipped[:,:,1],atol=1e-6)
            np.testing.assert_allclose(clipped[:,:,1],clipped[:,:,2],atol=1e-6)
            weights=np.array([.2126,.7152,.0722])
            np.testing.assert_allclose(np.sum(clipped*weights,-1),np.sum(preview*weights,-1),atol=1e-6)

    def test_raf_anchor_uses_capture_recipe_without_reapplying_camera_wb(self):
        metadata={'FilmMode':'Classic Negative','DevelopmentDynamicRange':400,
                  'HighlightTone':'-2 (soft)','ShadowTone':'+2 (hard)',
                  'ColorChromeEffect':'Strong','WhiteBalanceFineTune':'Red +40, Blue -60'}
        a=np.full((3,4,3),.1,np.float32)
        def estimate(linear,reference,develop):
            develop(linear)
            return {'reference_ev':0.,'reference_matched':True}
        _preview_source.cache_clear()
        with patch('kora.studio.exif',return_value=metadata), \
             patch('kora.studio._decode_sensor',return_value=(a,a.copy())), \
             patch('kora.studio.estimate_reference_ev',side_effect=estimate), \
             patch('kora.studio.render',return_value=a) as render:
            _preview_source(Path('capture.RAF'),0,0)
            recipe=render.call_args.args[1]
            self.assertEqual((recipe.film,recipe.highlights,recipe.whites,recipe.shadows,recipe.blacks,recipe.dynamic_range),
                             ('classic_negative',-50,0,-50,0,400))
            self.assertEqual(recipe.color_chrome,'strong')
            self.assertEqual((recipe.wb,recipe.wb_red,recipe.wb_blue),('camera',0,0))
            self.assertTrue(render.call_args.kwargs['context']['source_exposure_anchor'])
        _preview_source.cache_clear()

    def test_exposure_anchor_retains_previous_highlight_response(self):
        from kora.recipe_effects import linear_tone_curve
        source=np.repeat(np.array([.08,.18,.5,1.,2.,4.,8.],np.float32)[None,:,None],3,-1)
        expected=[.08,.18,.43054205,.66410637,1.0175209,1.5590107,2.3886626]
        anchor=linear_tone_curve(source,highlights=-50,legacy_highlights=True)
        np.testing.assert_allclose(anchor[0,:,0],expected,rtol=1e-6)
        self.assertGreater(float(abs(anchor-linear_tone_curve(source,highlights=-50)).max()),.01)

    def test_fuji_capture_dr_is_independent_of_recipe(self):
        for dr,gain in [(100,1),(200,2),(400,4)]:
            self.assertEqual(source_exposure({'DevelopmentDynamicRange':dr},'.RAF')['gain'],gain)

    def test_dng_baseline_takes_precedence_over_fuji_makernotes(self):
        m={'BaselineExposure':1.5,'DevelopmentDynamicRange':400,'BaselineExposureOffset':2}
        self.assertAlmostEqual(source_exposure(m,'.DNG')['gain'],2**1.5)
        self.assertEqual(source_exposure({'BaselineExposure':-1},'.dng')['gain'],.5)
        for val in [None,'invalid',float('nan'),float('inf'),100]:
            self.assertEqual(source_exposure({'BaselineExposure':val},'.dng')['gain'],1)
        self.assertEqual(source_exposure({},'.raf')['gain'],1)

    def test_preview_and_export_apply_baseline_once_without_clipping(self):
        raw=MagicMock()
        raw.__enter__.return_value=raw
        raw.white_level=16383;raw.black_level_per_channel=[512]*4
        raw.extract_thumb.side_effect=OSError('no preview')
        raw.postprocess.return_value=np.full((2,3,3),4096,np.uint16)
        _preview_source.cache_clear()
        with tempfile.TemporaryDirectory() as tmp,patch('kora.studio.exif',return_value={'BaselineExposure':2}),patch('kora.studio.rawpy.imread',return_value=raw):
            path=Path(tmp)/'test.dng';path.write_bytes(b'fixture')
            for preview in (True,False):
                a=decode(path,preview=preview)
                np.testing.assert_allclose(a,4*8*4096/65535)
                self.assertEqual(raw.postprocess.call_args.kwargs['user_sat'],512+8*(16383-512))
                self.assertTrue(raw.postprocess.call_args.kwargs['no_auto_bright'])

    def test_reference_estimation_recovers_exposure_and_preserves_dark_scenes(self):
        a=np.repeat(np.linspace(.002,.15,100,dtype=np.float32)[None,:,None],3,-1)
        develop=lambda a:np.clip(a,0,1)**(1/2.2)
        reference=develop(a*2)
        fit=estimate_reference_ev(a,reference,develop)
        self.assertAlmostEqual(fit['reference_ev'],1,delta=.02)
        self.assertLess(fit['reference_rmse_after'],fit['reference_rmse_before']/20)
        dark=estimate_reference_ev(a,develop(a/2),develop)
        self.assertAlmostEqual(dark['reference_ev'],-1,delta=.02)
        self.assertFalse(estimate_reference_ev(a,np.zeros_like(a),develop)['reference_matched'])
