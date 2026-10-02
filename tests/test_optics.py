import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from kora.optics import parse_warp, warp_coordinates, apply_corrections, lensfun_match, database


def opcode(coeff=(1,0,0,0,0,0),center=(.5,.5)):
    payload=struct.pack('>I8d',1,*coeff,*center)
    return struct.pack('>5I',1,1,0x01030000,0,len(payload))+payload


class OpticsTests(unittest.TestCase):
    def test_recent_database_and_resolved_lens_names(self):
        db=database()
        if db is None:self.skipTest('Optional optics dependency absent')
        self.assertGreaterEqual(len(db.lenses),1569)
        self.assertGreaterEqual(len(db.cameras),1057)
        samples=[
            ({'Make':'FUJIFILM','Model':'X-M5','LensModel':'XC15-45mmF3.5-5.6 OIS PZ'},'XC15-45mmF3.5-5.6 OIS PZ'),
            ({'Make':'Canon','Model':'Canon EOS R5','LensModel':'50mm F1.4 DG HSM | Art 014','LensID':'Sigma 50mm f/1.4 DG HSM | A'},'Sigma 50mm f/1.4 DG HSM [A]'),
            ({'Make':'FUJIFILM','Model':'X100VI','LensModel':'23.0 mm f/2.0'},'X100V & compatibles'),
            ({'Make':'NIKON CORPORATION','Model':'COOLPIX P1000'},'Coolpix P1000 & compatibles'),
            ({'Make':'SONY','Model':'ILCE-7M4','LensModel':'FE 50mm F2.5 G'},'FE 50mm f/2.5 G')]
        for meta,expected in samples:
            with self.subTest(meta=meta):
                match=lensfun_match(meta);self.assertIsNotNone(match);self.assertEqual(match[1].model,expected)

    def test_ambiguous_id_numeric_id_and_unprofiled_lenses_are_not_guessed(self):
        if database() is None:self.skipTest('Optional optics dependency absent')
        for meta in (
            {'Make':'Canon','Model':'Canon EOS 5D Mark IV','LensModel':'24-70mm','LensID':'Sigma 24-70mm f/2.8 IF EX DG HSM or Tamron SP 24-70mm f/2.8 Di VC USD'},
            {'Make':'Canon','Model':'Canon EOS R5','LensID':368},
            {'Make':'Hasselblad','Model':'X2D 100C','LensModel':'XCD 38V'},
            {'Make':'FUJIFILM','Model':'GFX 50S','LensModel':'GF63mmF2.8 R WR'},
            {'Make':'FUJIFILM','Model':'X-M5','LensModel':'Unidentified'},
        ):
            with self.subTest(meta=meta):self.assertIsNone(lensfun_match(meta))

    def test_multiple_calibrations_require_same_identity_and_unique_crop_match(self):
        from kora.optics import _best_calibration
        camera=SimpleNamespace(crop_factor=1.5)
        wide=SimpleNamespace(maker='Test',model='Test 24mm f/2',crop_factor=1.)
        crop=SimpleNamespace(maker='Test',model='Test 24mm f/2',crop_factor=1.5)
        other=SimpleNamespace(maker='Test',model='Test 24mm f/2 II',crop_factor=1.5)
        self.assertIs(_best_calibration([wide,crop],camera),crop)
        self.assertIsNone(_best_calibration([crop,other],camera))
        self.assertIsNone(_best_calibration([crop,crop],camera))

    def test_regional_dng_correction_matches_full_frame_and_sparse_statistics(self):
        from kora.optics import dng_corrected_region
        source=np.random.default_rng(8).uniform(-.2,4,(83,117,3)).astype(np.float32)
        for coefficient in (-.1,.08):
            for orientation,k in ((1,0),(3,2),(6,3),(8,1)):
                with self.subTest(coefficient=coefficient,orientation=orientation):
                    a=np.rot90(source,k)
                    profile={'orientation':orientation,'source':'dng-warp','distortion':True,
                             'warp':parse_warp(opcode((1,coefficient,0,0,0,0),(.4,.55)))}
                    full=apply_corrections(a,profile,'auto')
                    for box in ((0,0,30,25),(21,17,65,60),(0,0,a.shape[1],a.shape[0])):
                        x0,y0,x1,y1=box
                        np.testing.assert_allclose(dng_corrected_region(a,profile,box),full[y0:y1,x0:x1],atol=1e-6)
                    sparse=dng_corrected_region(a,profile,(0,0,a.shape[1],a.shape[0]),7)
                    np.testing.assert_allclose(sparse,full[::7,::7],atol=1e-6)

    def test_identity_and_radial_mapping_follow_dng_coordinates(self):
        xy=warp_coordinates(101,81,0,81,parse_warp(opcode()))
        yy,xx=np.mgrid[:81,:101]
        np.testing.assert_allclose(xy[...,0],xx,atol=1e-5)
        np.testing.assert_allclose(xy[...,1],yy,atol=1e-5)
        # At a corner r=1; radial factor .9 maps (0,0) to (5,4).
        warp=parse_warp(opcode((1,-.1,0,0,0,0)))
        np.testing.assert_allclose(warp_coordinates(101,81,0,1,warp)[0,0],[5,4],atol=1e-5)

    def test_invalid_or_unhandled_opcodes_are_rejected(self):
        for b in (b'',opcode()[:-1],opcode()+b'extra',opcode((float('nan'),0,0,0,0,0)),
                  opcode((1,0,0,0,.1,0)),opcode((1,-1,0,0,0,0)),opcode(center=(2,.5))):
            with self.subTest(data=len(b)),self.assertRaises(ValueError):parse_warp(b)

    def test_off_is_bit_exact_and_active_preserves_hdr_and_source(self):
        a=np.random.default_rng(2).uniform(-.1,4,(64,96,3)).astype(np.float32);saved=a.copy()
        profile={'orientation':1,'source':'dng-warp','distortion':True,'vignetting':False,
                 'warp':parse_warp(opcode((1,-.1,0,0,0,0)))}
        self.assertIs(apply_corrections(a,profile),a)
        b=apply_corrections(a,profile,'auto')
        np.testing.assert_array_equal(a,saved)
        self.assertEqual(b.shape,a.shape);self.assertGreater(float(b.max()),1)
        self.assertTrue(np.isfinite(b).all());self.assertGreater(float(abs(b-a).mean()),.1)
        np.testing.assert_allclose(apply_corrections(np.full_like(a,3),profile,'auto'),3)

    def test_portrait_rotation_uses_sensor_axes(self):
        a=np.random.default_rng(1).uniform(0,1,(63,95,3)).astype(np.float32)
        profile={'orientation':1,'source':'dng-warp','distortion':True,
                 'warp':parse_warp(opcode((1,-.1,0,0,0,0),(.4,.55)))}
        expected=apply_corrections(a,profile,'auto')
        for orientation,k in ((3,2),(6,3),(8,1)):
            result=apply_corrections(np.rot90(a,k),{**profile,'orientation':orientation},'auto')
            np.testing.assert_allclose(result,np.rot90(expected,k),atol=1e-6)

    def test_unknown_profile_does_not_guess_or_change_pixels(self):
        a=np.ones((8,9,3),np.float32)
        self.assertIs(apply_corrections(a,{'distortion':False,'vignetting':False},'auto','auto'),a)
        with patch('kora.optics.database',return_value=None):
            self.assertIsNone(lensfun_match({'Make':'Unknown','Model':'Unknown'}))

    def test_lensfun_profile_corrects_vignetting_without_clipping_hdr(self):
        if database() is None:self.skipTest('Optional optics dependency absent')
        meta={'Make':'Canon','Model':'Canon EOS R6m2','LensModel':'EF16-35mm f/2.8L III USM'}
        self.assertIsNotNone(lensfun_match(meta))
        profile={'source':'lensfun','orientation':1,'metadata':meta,'distortion':True,
                 'vignetting':True,'focal':26.,'aperture':2.8}
        a=np.full((80,120,3),2.,np.float32)
        b=apply_corrections(a,profile,'auto','auto')
        self.assertGreater(b[0,0,0],b[40,60,0]*1.2)
        self.assertTrue(np.isfinite(b).all());np.testing.assert_array_equal(a,2.)
