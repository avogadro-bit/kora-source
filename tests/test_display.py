import unittest
from io import BytesIO
import numpy as np
import tifffile
from PIL import Image,ImageCms,JpegImagePlugin
from kora.studio import StudioRecipe,render,encode,srgb_encode,transform_output,_resize_float_to


class DisplayTests(unittest.TestCase):
    def test_resampled_display_values_saturate_instead_of_wrapping(self):
        # Fractional crop/zoom alignment resamples already-rendered pixels.
        # Lanczos lobes can cross either endpoint, even with valid input RGB.
        source=np.zeros((96,129,3),np.float32)
        source[:,17:65]=[1,.5,0]
        source[:,65:113]=[0,.5,1]
        pixels=_resize_float_to(source,(128,96))
        self.assertLess(pixels.min(),-.5/255)
        self.assertGreater(pixels.max(),1+.5/255)
        before=pixels.copy()
        for file_type,preview,detail in [('jpeg',True,False),('tiff16',True,True),
                                         ('jpeg',False,False),('tiff8',False,False),
                                         ('tiff16',False,False)]:
            with self.subTest(file_type=file_type,preview=preview,detail=detail):
                recipe=StudioRecipe(file_type=file_type)
                actual,mime=encode(pixels,recipe,preview=preview,detail=detail)
                bounded,_=encode(np.clip(pixels,0,1),recipe,preview=preview,detail=detail)
                read=(lambda data:tifffile.imread(BytesIO(data))) if mime=='image/tiff' else (lambda data:np.asarray(Image.open(BytesIO(data))))
                np.testing.assert_array_equal(read(actual),read(bounded))
        np.testing.assert_array_equal(pixels,before)

    def test_reduced_export_preserves_black_white_and_integer_precision(self):
        source=np.zeros((90,181,3),np.float32)
        source[:,::3]=[1,.002,.998]
        source[:,1::3]=[0,.998,.002]
        pixels=transform_output(source,StudioRecipe(aspect='1:1',image_size='M'))
        self.assertTrue(np.any((pixels<0)|(pixels>1)))
        for file_type,dtype in [('tiff8',np.uint8),('tiff16',np.uint16)]:
            with self.subTest(file_type=file_type):
                payload,_=encode(pixels,StudioRecipe(file_type=file_type))
                actual=tifffile.imread(BytesIO(payload))
                expected=np.rint(np.clip(pixels,0,1)*np.iinfo(dtype).max).astype(dtype)
                np.testing.assert_array_equal(actual,expected)

    def test_detail_transport_keeps_colour_samples_and_srgb_for_tiff_recipes(self):
        # Thin coloured edges expose JPEG chroma subsampling even when its
        # luminance resolution is correct. Display tiles always use sRGB JPEG.
        a=np.zeros((64,96,3),np.float32);a[:,::2]=[.8,.1,.4];a[:,1::2]=[.1,.5,.8]
        recipe=StudioRecipe(file_type='tiff16',color_space='adobe_rgb')
        payload,mime=encode(a,recipe,preview=True,detail=True)
        image=Image.open(BytesIO(payload))
        self.assertEqual(mime,'image/jpeg');self.assertEqual(image.size,(96,64))
        self.assertEqual(JpegImagePlugin.get_sampling(image),0)
        profile=ImageCms.ImageCmsProfile(BytesIO(image.info['icc_profile']))
        self.assertIn('sRGB',ImageCms.getProfileDescription(profile))
        self.assertLess(float(np.mean(abs(np.asarray(image,dtype=np.float32)/255-a))),.012)

    def test_raw_base_comparison_keeps_crop_and_output_size(self):
        a=np.random.default_rng(33).uniform(0,.8,(200,300,3)).astype(np.float32)
        recipe=StudioRecipe(digital_crop=2,aspect='1:1',image_size='M')
        full=render(a,recipe,neutral=True)
        expected=transform_output(np.clip(srgb_encode(a),0,1),recipe)
        np.testing.assert_array_equal(full,expected)
        self.assertEqual(full.shape,(71,71,3))
        region=render(a,recipe,neutral=True,output_transform=False)
        self.assertEqual(region.shape,a.shape)
