from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import tempfile
import time
import unittest
from unittest.mock import patch
from kora.external_tools import read_exiftool, find_exiftool
from kora.raw import exif, _cached_exif


class MetadataPortabilityTests(unittest.TestCase):
    def setUp(self):
        _cached_exif.cache_clear()

    def test_windows_utf8_path_does_not_use_system_code_page_or_console(self):
        name='C:\\Photos été\\東京 01.DNG'
        payload='[{"Model":"Appareil été 東京"}]'.encode('utf-8')
        with patch('kora.external_tools.sys.platform','win32'), \
             patch('subprocess.run',return_value=SimpleNamespace(stdout=payload)) as run:
            self.assertIn('été 東京',read_exiftool('exiftool.exe',name,['-j']))
        args=run.call_args
        self.assertEqual(args.kwargs['input'],(name+'\n').encode('utf-8'))
        self.assertEqual(args.kwargs['creationflags'],0x08000000)
        self.assertNotIn(name,args.args[0])
        self.assertEqual(args.args[0][-4:],['-charset','filename=utf8','-@','-'])

    def test_unix_newline_remains_one_argument_and_binary_is_unmodified(self):
        name='/photos/line\nbreak.DNG';blob=b'\x00\xff\x80'
        with patch('kora.external_tools.sys.platform','darwin'), \
             patch('subprocess.run',return_value=SimpleNamespace(stdout=blob)) as run:
            self.assertEqual(read_exiftool('exiftool',name,['-b'],binary=True),blob)
        self.assertEqual(run.call_args.args[0],['exiftool','-b',name])
        with patch('kora.external_tools.sys.platform','win32'), patch('subprocess.run') as run:
            with self.assertRaises(ValueError):read_exiftool('exiftool',name,['-j'])
            run.assert_not_called()

    def test_reuses_metadata_without_sharing_mutable_values_or_stale_file(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch('kora.raw.find_exiftool',return_value='exiftool'), \
             patch('kora.raw.read_exiftool',return_value='[{"EXIF:Model":"test","EXIF:Values":[1,2]}]') as read:
            photo=Path(tmp)/'photo.dng';photo.write_bytes(b'1')
            first=exif(photo);first['Values'][0]=99
            self.assertEqual(exif(photo)['Values'],[1,2]);self.assertEqual(read.call_count,1)
            photo.write_bytes(b'new file')
            self.assertEqual(exif(photo)['Model'],'test');self.assertEqual(read.call_count,2)
            with patch('kora.raw.find_exiftool',return_value='new-exiftool'):
                exif(photo)
            self.assertEqual(read.call_count,3)

    def test_simultaneous_requests_run_metadata_tool_once(self):
        def read(*args,**kwargs):time.sleep(.025);return '[{"EXIF:Model":"test"}]'
        with tempfile.TemporaryDirectory() as tmp, \
             patch('kora.raw.find_exiftool',return_value='exiftool'), \
             patch('kora.raw.read_exiftool',side_effect=read) as tool:
            photo=Path(tmp)/'photo.dng';photo.write_bytes(b'1')
            with ThreadPoolExecutor(max_workers=4) as pool:
                results=list(pool.map(lambda _:exif(photo),range(4)))
            self.assertTrue(all(r['Model']=='test' for r in results))
            self.assertEqual(tool.call_count,1)

    def test_windows_portable_tool_directory(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch('kora.external_tools.sys.platform','win32'), \
             patch('kora.external_tools.sys.frozen',True,create=True), \
             patch('kora.external_tools.sys.executable',str(Path(tmp)/'Kora.exe')):
            expected=Path(tmp)/'tools'/'exiftool.exe'
            with patch('kora.external_tools.shutil.which',side_effect=lambda p:str(expected) if p==str(expected) else None):
                self.assertEqual(find_exiftool(),str(expected.resolve()))

    def test_lens_inspection_recovers_after_optional_tool_is_installed(self):
        from kora.optics import _inspect
        _inspect.cache_clear()
        photo=Path('/photos/test.dng')
        with patch('kora.optics.find_exiftool',return_value=None):
            self.assertIn('ExifTool missing',_inspect(photo,0,0)['label'])
        with patch('kora.optics.find_exiftool',return_value='exiftool'), \
             patch('kora.optics.read_exiftool',return_value='[{"Make":"Other","Model":"Test"}]') as read:
            self.assertNotIn('ExifTool missing',_inspect(photo,0,0)['label'])
            read.assert_called_once()
        _inspect.cache_clear()
