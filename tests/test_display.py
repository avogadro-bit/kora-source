import unittest
from io import BytesIO
import numpy as np
from PIL import Image,ImageCms,JpegImagePlugin
from kora.studio import StudioRecipe,render,encode,srgb_encode,transform_output


class DisplayTests(unittest.TestCase):
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
