import unittest
from kora.official_luts import missing_luts
import numpy as np
from kora.camera_white_balance import camera_to_srgb, apply_sensor_gains
from kora.studio import StudioRecipe, render


class CameraWhiteBalanceTests(unittest.TestCase):
    def matrix(self):
        # Publicly representable calibration matrix, checked against LibRaw's
        # camera-RGB and sRGB decodes of the same X-M5 RAW (linear 16-bit).
        return camera_to_srgb([[1.2836,-.5909,-.1032],
                               [-.3087,1.1132,.2236],[-.0035,.0872,.533]])

    def test_matrix_matches_independent_decoder_measurement(self):
        np.testing.assert_allclose(self.matrix(),
            [[1.302964,-.201125,-.020778],[-.008118,1.625324,-.395129],
             [-.294846,-.424200,1.415907]],atol=.0003)
        np.testing.assert_allclose(np.ones(3)@self.matrix(),np.ones(3),atol=1e-6)
        for matrix in (np.zeros((3,3)),np.full((3,3),np.nan),np.ones((3,3))):
            with self.assertRaises(ValueError):camera_to_srgb(matrix)

    def test_sensor_wb_preserves_signed_values_and_highlight_headroom(self):
        matrix=self.matrix();sensor=np.array([[[.01,.5,3.],[2.,1.,.2]]],np.float32)
        rgb=np.einsum('...i,ij->...j',sensor,matrix)
        gains=np.array([1.3,1,.7],np.float32)
        expected=np.einsum('...i,ij->...j',sensor*gains,matrix)
        actual=apply_sensor_gains(rgb,gains,matrix)
        np.testing.assert_allclose(actual,expected,atol=1e-6)
        self.assertLess(actual.min(),0);self.assertGreater(actual.max(),1)
        self.assertIs(apply_sensor_gains(rgb,np.ones(3),matrix),rgb)

    @unittest.skipIf(missing_luts(),'Official LUTs unavailable')
    def test_auto_uses_source_illuminant_and_does_not_rebalance_the_subject(self):
        source=np.broadcast_to(np.array([.6,.2,.05],np.float32),(20,30,3)).copy()
        context={'camera_to_srgb':self.matrix(),'camera_wb_gains':{'auto':np.ones(3)}}
        recipe=StudioRecipe(film='provia',noise_reduction=-4)
        expected=render(source,recipe,context=context)
        actual=render(source,recipe.model_copy(update={'wb':'auto'}),context=context)
        np.testing.assert_array_equal(actual,expected)
        self.assertGreater(abs(render(source,recipe.model_copy(update={'wb':'auto'}))-expected).mean(),.01)

    @unittest.skipIf(missing_luts(),'Official LUTs unavailable')
    def test_preview_and_tile_use_the_same_sensor_shift(self):
        source=np.random.default_rng(27).uniform(.01,.6,(90,100,3)).astype(np.float32)
        recipe=StudioRecipe(wb_red=4,wb_blue=-5,noise_reduction=-4)
        context={'camera_to_srgb':self.matrix(),'full_shape':source.shape}
        full=render(source,recipe,context=context)
        tile=render(source[15:55,20:70],recipe,context=context,output_transform=False)
        np.testing.assert_array_equal(tile,full[15:55,20:70])
