import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
import numpy as np
from kora.source_white_balance import fuji_shift,source_white_balance
from kora.studio import _decode_sensor,_preview_source,shooting_settings,StudioRecipe


class SourceWhiteBalanceTests(unittest.TestCase):
    def metadata(self):
        return {'Make':'FUJIFILM','Model':'X-M5','WhiteBalance':'Auto',
                'WhiteBalanceFineTune':'Red +80, Blue -100',
                'WB_GRBLevelsAuto':'302 573 533'}

    def tearDown(self):
        _preview_source.cache_clear()

    def test_shift_units_and_rgbg_order(self):
        m=self.metadata();self.assertEqual(fuji_shift(m),(4,-5))
        plan=source_white_balance(m,'.RAF')
        self.assertTrue(plan['shift_removed'])
        self.assertEqual(plan['user_wb'],[573,302,533,302])
        m.pop('WB_GRBLevelsAuto');m['WB_GRGBLevelsAuto']='302 573 303 533'
        self.assertEqual(source_white_balance(m,'.raf')['user_wb'],[573,302,533,303])

    def test_no_guessed_correction_for_other_modes_or_missing_coefficients(self):
        for mode in ('Kelvin','Daylight','Custom','Auto (white priority)','Auto (ambiance priority)'):
            m={**self.metadata(),'WhiteBalance':mode}
            self.assertFalse(source_white_balance(m,'.raf')['shift_removed'])
            self.assertIn('warning',source_white_balance(m,'.raf'))
        m=self.metadata();m.pop('WB_GRBLevelsAuto')
        self.assertFalse(source_white_balance(m,'.raf')['shift_removed'])
        for value in ('0 573 533','302 nan 533','302 573','302 999999 533',None):
            self.assertFalse(source_white_balance({**m,'WB_GRBLevelsAuto':value},'.raf')['shift_removed'])

    def test_zero_shift_and_non_fuji_sources_are_unchanged(self):
        m={**self.metadata(),'WhiteBalanceFineTune':'Red +0, Blue +0'}
        self.assertFalse(source_white_balance(m,'.raf')['shift_removed'])
        for suffix in ('.dng','.cr3','.nef'):
            self.assertEqual(source_white_balance(self.metadata(),suffix),
                             {'shift_removed':False,'basis':'camera as shot','user_wb':None})
        for value in ('Red +4, Blue -5','Red +200, Blue +0','invalid',None):
            self.assertIsNone(fuji_shift({'WhiteBalanceFineTune':value}))

    def test_both_decoder_sizes_use_explicit_sensor_wb(self):
        raw=MagicMock();raw.__enter__.return_value=raw
        raw.white_level=16383;raw.black_level_per_channel=[512]*4
        raw.postprocess.return_value=np.full((4,6,3),4096,np.uint16)
        raw.extract_thumb.side_effect=OSError('no thumbnail')
        wb=source_white_balance(self.metadata(),'.raf')['user_wb']
        with tempfile.TemporaryDirectory() as directory,patch('kora.studio.rawpy.imread',return_value=raw):
            path=Path(directory)/'image.RAF';path.write_bytes(b'fixture')
            for preview in (True,False):
                _decode_sensor(path,preview,user_wb=wb)
                args=raw.postprocess.call_args.kwargs
                self.assertFalse(args['use_camera_wb'])
                self.assertFalse(args['use_auto_wb'])
                self.assertEqual(args['user_wb'],wb)
                self.assertEqual(args['half_size'],preview)
            _decode_sensor(path)
            self.assertTrue(raw.postprocess.call_args.kwargs['use_camera_wb'])
            self.assertNotIn('user_wb',raw.postprocess.call_args.kwargs)

    def test_exposure_anchor_keeps_capture_wb_separate_from_neutral_output(self):
        _preview_source.cache_clear()
        neutral=np.full((3,4,3),.2,np.float32)
        shifted=np.full((3,4,3),.4,np.float32)
        def estimate(pixels,reference,develop):
            np.testing.assert_array_equal(pixels,shifted)
            develop(pixels)
            return {'reference_ev':.5,'reference_matched':True}
        with patch('kora.studio.exif',return_value=self.metadata()), \
             patch('kora.studio._decode_sensor',side_effect=[(neutral.copy(),neutral),(shifted.copy(),neutral)]) as decoder, \
             patch('kora.studio.estimate_reference_ev',side_effect=estimate), \
             patch('kora.studio.render',return_value=neutral) as renderer:
            output,info=_preview_source(Path('image.RAF'),0,0)
        np.testing.assert_allclose(output,neutral*2**.5)
        self.assertEqual(decoder.call_args_list[0].kwargs['user_wb'],[573,302,533,302])
        self.assertNotIn('user_wb',decoder.call_args_list[1].kwargs)
        self.assertTrue(info['white_balance']['shift_removed'])
        self.assertIn('without R/B shift',info['normalization']['label'])
        self.assertEqual(renderer.call_args.args[1].wb_red,0)
        self.assertEqual(renderer.call_args.args[1].wb_blue,0)

    def test_capture_shifts_only_restored_when_neutralization_was_applied(self):
        m=self.metadata()
        self.assertEqual(shooting_settings(m)['wb_red'],0)
        recipe=StudioRecipe(**shooting_settings(m,restore_wb_shift=True))
        self.assertEqual((recipe.wb_red,recipe.wb_blue),(4,-5))
        self.assertEqual((StudioRecipe().wb_red,StudioRecipe().wb_blue),(0,0))
