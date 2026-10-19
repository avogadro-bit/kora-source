from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
from kora import diagnostics
from kora.external_tools import ExifToolError, read_exiftool, find_exiftool
from kora.raw import exif, _cached_exif

# Exact failure of the bundled ExifTool 13.59 launcher under a non-ANSI folder.
PERL_FAILURE=subprocess.CalledProcessError(1,['exiftool.exe'],output=b'',stderr=(
    b'Could not find C:\\Program Files\\KORA\\tools\\exiftool_files\\perl5*.dll\r\n'))


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

    def test_failed_run_reports_exiftool_message(self):
        for failure,message in ((PERL_FAILURE,'status 1: Could not find C:\\Program Files'),
                                (subprocess.TimeoutExpired('exiftool',20),'did not run'),
                                (FileNotFoundError(2,'missing'),'did not run')):
            with self.subTest(failure=type(failure).__name__), \
                 patch('subprocess.run',side_effect=failure):
                with self.assertRaises(ExifToolError) as raised:
                    read_exiftool('exiftool.exe','photo.raf',['-j'])
                self.assertIn(message,str(raised.exception))
                self.assertIsInstance(raised.exception,RuntimeError)

    def test_failed_exiftool_falls_back_like_missing_and_is_logged_once(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(diagnostics,'log_path',return_value=Path(tmp)/'errors.jsonl'), \
             patch('kora.raw.find_exiftool',return_value='exiftool.exe'), \
             patch('subprocess.run',side_effect=PERL_FAILURE) as run:
            photo=Path(tmp)/'KŌRA photo.raf';photo.write_bytes(b'1')
            self.assertEqual(exif(photo),{'metadata_available':False,'reason':'ExifTool failed'})
            self.assertEqual(exif(photo)['reason'],'ExifTool failed')
            self.assertEqual(run.call_count,1)
            events=[json.loads(line) for line in (Path(tmp)/'errors.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertEqual([e['operation'] for e in events],['exiftool-metadata'])
        self.assertIn('ExifToolError: ExifTool exited with status 1: Could not find [path]',events[0]['error'])
        self.assertNotIn('KORA',events[0]['error'])

    def test_failed_exiftool_keeps_basic_dng_metadata(self):
        import tifffile
        with tempfile.TemporaryDirectory() as tmp, \
             patch('kora.raw.record_error') as record, \
             patch('kora.raw.find_exiftool',return_value='exiftool.exe'), \
             patch('kora.raw.read_exiftool',side_effect=ExifToolError('ExifTool exited with status 1')):
            photo=Path(tmp)/'photo.dng'
            tifffile.imwrite(photo,[[0]],dtype='uint16',extratags=[(271,'s',0,'Leica',True),(272,'s',0,'M11',True)])
            result=exif(photo)
        self.assertEqual((result['Make'],result['Model'],result['metadata_source']),('Leica','M11','DNG tags'))
        self.assertTrue(result['metadata_available'])
        record.assert_called_once()
        self.assertEqual(record.call_args.args[0],'exiftool-metadata')

    def test_lens_inspection_falls_back_when_exiftool_fails(self):
        from kora.optics import _inspect
        _inspect.cache_clear()
        self.addCleanup(_inspect.cache_clear)
        with patch('kora.optics.find_exiftool',return_value='exiftool.exe'), \
             patch('kora.optics.record_error') as record, \
             patch('subprocess.run',side_effect=PERL_FAILURE):
            result=_inspect(Path('/photos/test.raf'),0,0)
        self.assertEqual(result['label'],'ExifTool failed: lens profile unavailable')
        self.assertFalse(result['distortion'] or result['vignetting'])
        self.assertEqual(record.call_args.args[0],'exiftool-optics')

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
