import unittest
from types import SimpleNamespace
import numpy as np
from kora.highlight_recovery import (bayer_clipping, recover_camera_highlights,
                                     clipped_neutral_mask, neutralize_clipped_rgb)


class HighlightRecoveryTests(unittest.TestCase):
    def test_balanced_clipped_white_is_neutral_but_saturated_colour_survives(self):
        raw=SimpleNamespace(raw_image_visible=np.array([[5000,10000],[10000,6667]],np.uint16),
            raw_pattern=np.array([[0,1],[3,2]]),color_desc=b'RGBG',
            camera_whitebalance=[2,1,1.5,1],black_level_per_channel=[0]*4,
            white_level=10000,sizes=SimpleNamespace(flip=0))
        self.assertAlmostEqual(float(clipped_neutral_mask(raw)[0,0]),1)
        # Clipped red with a low blue channel is a colour, not a white patch.
        raw.raw_image_visible[:]=[[10000,4000],[4000,100]]
        np.testing.assert_array_equal(clipped_neutral_mask(raw),0)
        # Bright but intact white must also retain its measured colour.
        raw.raw_image_visible[:]=[[4500,9000],[9000,6000]]
        np.testing.assert_array_equal(clipped_neutral_mask(raw),0)

    def test_neutralization_preserves_luminance_headroom_and_source(self):
        rgb=np.full((12,24,3),[6,2,5],np.float32);before=rgb.copy()
        mask=np.ones((6,12),np.float32)
        out=neutralize_clipped_rgb(rgb,mask,preview=True)
        np.testing.assert_allclose(out[...,0],out[...,1],atol=1e-6)
        np.testing.assert_allclose(out[...,1],out[...,2],atol=1e-6)
        weights=np.array([.2126,.7152,.0722],np.float32)
        np.testing.assert_allclose(out@weights,rgb@weights,atol=1e-6)
        self.assertGreater(float(out.min()),1)
        np.testing.assert_array_equal(rgb,before)
        for empty in (None,np.zeros_like(mask)):
            np.testing.assert_array_equal(neutralize_clipped_rgb(rgb,empty,preview=True),rgb)

    def test_generic_mask_skips_non_bayer_and_handles_rotation_and_user_wb(self):
        raw=SimpleNamespace(raw_image_visible=np.tile([[5000,10000],[10000,6667]],(2,3)).astype(np.uint16),
            raw_pattern=np.array([[0,1],[3,2]]),color_desc=b'RGBG',
            camera_whitebalance=[2,1,1.5,0],black_level_per_channel=[0]*4,
            white_level=10000,sizes=SimpleNamespace(flip=6))
        self.assertEqual(clipped_neutral_mask(raw).shape,(3,2))
        np.testing.assert_array_equal(clipped_neutral_mask(raw),1)
        np.testing.assert_array_equal(clipped_neutral_mask(raw,[1,1,1,1]),0)
        self.assertIsNone(clipped_neutral_mask(raw,[float('nan'),1,1,1]))
        raw.raw_pattern=np.zeros((6,6),int)
        self.assertIsNone(clipped_neutral_mask(raw))
        raw.raw_pattern=None
        self.assertIsNone(clipped_neutral_mask(raw))

    def test_donors_with_another_clipped_channel_cannot_tint_recovery(self):
        camera=np.empty((96,160,3),np.float32);camera[:]=[16000,12000,16000]
        mask=np.zeros_like(camera);mask[...,2]=1
        # Fully valid bright donors describe a 1:2:1 surface. The much larger
        # partially clipped region must not contaminate its reconstruction.
        camera[:,:40]=[6000,12000,6000];mask[:,:40]=0
        camera[:,100:]=[12000,16000,12000];mask[:,100:]=[0,1,0]
        out=recover_camera_highlights(camera,mask)
        np.testing.assert_allclose(out[:,100:,1],24000,rtol=.004)

    def test_uncertain_colour_fades_before_last_channel_clips(self):
        values=np.linspace(.55,1,1001,dtype=np.float32)
        sensor=np.empty((2,2002),np.uint16)
        sensor[0,::2]=np.round(512+values*(16383-512))
        sensor[0,1::2]=16383;sensor[1,::2]=16383;sensor[1,1::2]=16383
        raw=SimpleNamespace(raw_image_visible=sensor,raw_pattern=np.array([[0,1],[3,2]]),
                            black_level_per_channel=[512]*4,white_level=16383,
                            sizes=SimpleNamespace(flip=0))
        clip,neutral=bayer_clipping(raw,with_neutralization=True)
        np.testing.assert_array_equal(clip,bayer_clipping(raw))
        self.assertEqual(float(neutral[0,0]),0)
        self.assertEqual(float(neutral[0,-1]),1)
        self.assertTrue(np.all(np.diff(neutral)>=0))
        self.assertLess(float(np.diff(neutral).max()),.002)
        self.assertGreater(float(neutral[0,800]),.8)
        # No desaturation when all three colours still survive.
        sensor[:]=12000
        _,neutral=bayer_clipping(raw,with_neutralization=True)
        np.testing.assert_array_equal(neutral,0)
        sensor[0,::2]=16383;raw.sizes.flip=6
        _,neutral=bayer_clipping(raw,with_neutralization=True)
        self.assertEqual(neutral.shape,(1001,1))

    def test_two_green_sites_are_one_clipped_colour(self):
        raw=SimpleNamespace(raw_image_visible=np.array([[1000,16383],[16383,2000]],np.uint16),
                            raw_pattern=np.array([[0,1],[3,2]]),
                            black_level_per_channel=[512]*4,white_level=16383,
                            sizes=SimpleNamespace(flip=0))
        np.testing.assert_array_equal(bayer_clipping(raw),[[[0,1,0]]])
        raw.raw_image_visible[:]=16383
        np.testing.assert_array_equal(bayer_clipping(raw),1)

    def test_surviving_channels_restore_texture_without_gray_or_magenta(self):
        # Known warm surface with varying illumination and a clipped green
        # channel. Two green Bayer sites must not erase the intact red/blue.
        x=np.linspace(.2,1.4,256,dtype=np.float32)[None,:]
        true=np.stack([x*10000,x*18000,x*7000],-1)
        camera=np.minimum(true,16000)
        m=np.clip((true/16000-.94)/.06,0,1);m=m*m*(3-2*m)
        out=recover_camera_highlights(camera,m)
        np.testing.assert_allclose(out[...,[0,2]],camera[...,[0,2]],atol=.01)
        np.testing.assert_allclose(out,true,rtol=.003,atol=.05)
        self.assertTrue(np.all(np.diff(out[...,1],axis=1)>0))
        np.testing.assert_array_equal(out[:, :100],camera[:, :100])

    def test_fully_clipped_or_unclipped_input_is_finite_and_unchanged(self):
        for value,mask in ((120.,0.),(16000.,1.)):
            a=np.full((16,20,3),value,np.float32)
            out=recover_camera_highlights(a,np.full_like(a,mask))
            np.testing.assert_array_equal(out,a)

    def test_recovery_does_not_mutate_camera_or_mask(self):
        a=np.ones((32,32,3),np.float32)*1000
        mask=np.zeros_like(a);mask[10:20,10:20,1]=1
        before=a.copy();m=mask.copy()
        recover_camera_highlights(a,mask)
        np.testing.assert_array_equal(a,before)
        np.testing.assert_array_equal(mask,m)

    def test_clipped_sky_does_not_inherit_dark_green_poles(self):
        light=np.linspace(5000,28000,384,dtype=np.float32)[None,:,None]
        truth=np.broadcast_to(light*np.array([.5,1.,.8],np.float32),(64,384,3)).copy()
        truth[8:56,180:185]=[500,7000,700]
        truth[8:56,300:305]=[500,7000,700]
        camera=np.minimum(truth,16000)
        mask=np.clip((truth/16000-.94)/.06,0,1);mask=mask*mask*(3-2*mask)
        out=recover_camera_highlights(camera,mask)
        sky=np.ones(truth.shape[:2],bool)
        sky[8:56,180:185]=False;sky[8:56,300:305]=False
        np.testing.assert_allclose(out[sky],truth[sky],rtol=.004,atol=.1)
        np.testing.assert_array_equal(out[~sky],camera[~sky])

    def test_losing_last_colour_anchor_does_not_darken_white(self):
        light=np.linspace(5000,50000,1024,dtype=np.float32)[None,:,None]
        truth=light*np.array([.5,1.,.8],np.float32)
        camera=np.minimum(truth,16000)
        mask=np.clip((truth/16000-.94)/.06,0,1);mask=mask*mask*(3-2*mask)
        out=recover_camera_highlights(camera,mask)
        luma=np.sum(out*np.array([.2126,.7152,.0722]),axis=-1)
        self.assertGreaterEqual(float(np.min(np.diff(luma,axis=1))),-.02)
        self.assertGreater(float(luma[0,-1]),25000)
        self.assertTrue(np.all(np.isfinite(out)))
        self.assertLessEqual(float(np.max(out/camera)),4)

    def test_broad_recovery_is_consistent_at_preview_and_full_scale(self):
        light=np.linspace(5000,28000,384,dtype=np.float32)[None,:,None]
        camera=np.broadcast_to(light*np.array([.5,1.,.8],np.float32),(64,384,3)).copy()
        mask=np.clip((camera/16000-.94)/.06,0,1);mask=mask*mask*(3-2*mask)
        camera=np.minimum(camera,16000)
        preview=recover_camera_highlights(camera,mask)
        full=recover_camera_highlights(camera.repeat(2,0).repeat(2,1),mask.repeat(2,0).repeat(2,1))
        np.testing.assert_allclose(full[::2,::2],preview,rtol=.004,atol=.1)
