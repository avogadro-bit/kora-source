import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import numpy as np
import tifffile
from kora.raw import exif
from kora.source_exposure import source_exposure
from kora.raw import normalize_exif
from kora.studio import shooting_settings,StudioRecipe


class ShootingMetadataTests(unittest.TestCase):
    def test_exiftool_full_film_names(self):
        labels={'F0/Standard (Provia)':'provia',
                'F1b/Studio Portrait Smooth Skin Tone (Astia)':'astia',
                'F2/Fujichrome (Velvia)':'velvia', 'F4/Velvia':'velvia',
                'Bleach Bypass':'eterna_bleach', 'Nostalgic Neg':'nostalgic_negative'}
        for label,film in labels.items():
            with self.subTest(label=label):
                self.assertEqual(shooting_settings({'FilmMode':label})['film'],film)
        # Historical S-series portrait modes have no proven modern equivalent.
        self.assertNotIn('film',shooting_settings({'FilmMode':'F1/Studio Portrait'}))

    def test_dng_profile_survives_missing_exiftool(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'camera.dng'
            tifffile.imwrite(path, np.zeros((8, 8), dtype=np.uint16),
                extratags=[(271, 's', 0, 'LEICA CAMERA AG', False),
                           (272, 's', 0, 'LEICA M11', False),
                           (50730, '2i', 1, (-1, 2), False)])
            with patch('kora.raw.find_exiftool', return_value=None):
                metadata = exif(path)
            self.assertEqual(metadata['BaselineExposure'], -.5)
            self.assertEqual(metadata['Model'], 'LEICA M11')
            self.assertTrue(source_exposure(metadata, '.dng')['floating_camera_rgb'])

    def test_makernotes_win_over_lossy_standard_exif_in_either_order(self):
        pairs=[('FujiFilm:Sharpness','+1 (medium hard)'),('ExifIFD:Sharpness','Hard'),('FujiFilm:WhiteBalance','Kelvin'),('ExifIFD:WhiteBalance','Manual')]
        for data in (dict(pairs),dict(reversed(pairs))):
            meta=normalize_exif(data)
            self.assertEqual(meta['Sharpness'],'+1 (medium hard)')
            self.assertEqual(meta['WhiteBalance'],'Kelvin')
            self.assertEqual(shooting_settings(meta)['sharpness'],1)

    def test_acros_and_filters_are_read_from_saturation(self):
        for suffix,filter_name in [('', 'none'),(' Red Filter','red'),(' Yellow Filter','yellow'),(' Green Filter','green')]:
            recipe=StudioRecipe(**shooting_settings({'Saturation':'Acros'+suffix,'FilmMode':'Classic Chrome'}))
            self.assertEqual(recipe.film,'acros');self.assertEqual(recipe.mono_filter,filter_name)
            self.assertEqual(recipe.color,0)

    def test_capture_wb_shift_is_not_applied_twice(self):
        r=StudioRecipe(**shooting_settings({'WhiteBalanceFineTune':'Red +40, Blue -80','WhiteBalance':'Kelvin','Saturation':'+4 (highest)','HighlightTone':'-2 (soft)','ShadowTone':-.5}))
        self.assertEqual((r.wb,r.wb_red,r.wb_blue),('camera',0,0))
        self.assertEqual((r.color,r.highlight_tone,r.shadow_tone),(4,-2,-.5))
        self.assertEqual((r.highlights,r.whites,r.shadows,r.blacks),(0,0,0,0))
