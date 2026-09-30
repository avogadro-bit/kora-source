import unittest
from pathlib import Path
import tempfile
import numpy as np
from kora.input_profiles import camera_profile,validate_linear_input,normalization_details,apply_input_color,LEICA_Q3_43
from kora.gui import Library
from kora.source_exposure import source_exposure

class CommonInputTests(unittest.TestCase):
    def test_reference_color_is_scoped_to_q3_43_dng_and_preserves_headroom(self):
        pixels=np.array([[[-.2,.18,3.],[0.,0.,0.],[1.,1.,1.]]],np.float32)
        metadata={'Make':'LEICA CAMERA AG','Model':'LEICA Q3 43'}
        profile=source_exposure(metadata,'.DNG')
        self.assertEqual(profile['input_profile'],LEICA_Q3_43.key)
        actual=apply_input_color(pixels,profile['input_profile'])
        np.testing.assert_allclose(actual[0,0],[-.20037966,.18,2.9396148],atol=1e-7)
        self.assertLess(actual.min(),0);self.assertGreater(actual.max(),1)
        np.testing.assert_array_equal(actual[0,1],0)
        np.testing.assert_array_equal(pixels[0,2],1)
        for make,model,ext in [('LEICA','LEICA Q3','.dng'),('LEICA','LEICA Q2','.dng'),
                               ('LEICA','LEICA M11','.dng'),('Apple','iPhone 16 Pro','.dng'),
                               ('FUJIFILM','X-M5','.raf'),('Canon','LEICA Q3 43','.dng'),
                               ('LEICA','LEICA Q3 43','.raf')]:
            info=source_exposure({'Make':make,'Model':model},ext)
            self.assertIs(apply_input_color(pixels,info.get('input_profile')),pixels)
        d=normalization_details(metadata,'.dng',profile)
        self.assertFalse(d['fuji_color_calibrated'])
        self.assertFalse(d['color_refinement']['cross_scene_color_validation'])
        self.assertFalse(d['color_refinement']['exposure_offset_applied'])

    def test_camera_profile_is_scoped_to_leica_make(self):
        for m in [{'Make':'Canon','Model':'LEICA M11'}, {'Make':'Sony','Model':'ILCE-7M4'}]:
            self.assertIsNone(camera_profile(m))
        self.assertIsNotNone(camera_profile({'Make':' Leica Camera AG ','Model':'M11'}))

    def test_common_representation_keeps_signed_values_and_highlight_latitude(self):
        a=np.array([[[-.1,.18,4.]]],np.float64)
        b=validate_linear_input(a)
        self.assertEqual(b.dtype,np.float32)
        np.testing.assert_allclose(b,a)
        for bad in [np.zeros((2,2)),np.zeros((0,2,3)),np.zeros((2,2,4)),np.full((2,2,3),np.nan)]:
            with self.assertRaises(ValueError):validate_linear_input(bad)

    def test_generic_profile_honestly_reports_estimation(self):
        m={'Make':'Canon','Model':'Canon EOS R6m2'}
        e=source_exposure(m,'.cr3');self.assertEqual(e['gain'],1)
        d=normalization_details(m,'.cr3',{**e,'reference_matched':True})
        self.assertEqual(d['profile'],'generic-libraw')
        self.assertFalse(d['fuji_color_calibrated'])
        self.assertIn('preview',d['exposure_method'])
        self.assertFalse(d['embedded_pixels_used_in_output'])

    def test_multibrand_discovery_does_not_accept_rendered_jpegs(self):
        with tempfile.TemporaryDirectory() as root:
            for name in ['a.CR3','b.NEF','c.ARW','d.RW2','e.ORF','f.RAF','g.DNG','h.JPG']:
                (Path(root)/name).write_bytes(b'test fixture')
            files=Library([root],root).select_folder(root)['files']
            self.assertEqual({r['format'] for r in files},{'CR3','NEF','ARW','RW2','ORF','RAF','DNG'})
