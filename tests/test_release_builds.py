from pathlib import Path
import hashlib
import tarfile
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

from scripts import build_rawpy_openmp as rawpy_build
from scripts import build_windows_release as windows_build
from scripts.audit_windows_bundle import audit_bundle
from tests.test_portability import packaged_assets, write_pe

ROOT = Path(__file__).resolve().parents[1]


def fake_rawpy(version, openmp):
    return types.SimpleNamespace(__version__=version, flags={'OPENMP': openmp})


class RawpyReleaseGuardTests(unittest.TestCase):
    def check(self, module, require_patched):
        with patch.dict('sys.modules', {'rawpy': module}):
            return rawpy_build.require_release_rawpy(require_patched)

    def test_unpatched_openmp_decoder_is_refused_everywhere(self):
        for required in (False, True):
            with self.assertRaisesRegex(SystemExit, 'without the deterministic X-Trans patch'):
                self.check(fake_rawpy('0.27.1', True), required)

    def test_single_threaded_decoder_allowed_only_where_no_patched_build_is_required(self):
        self.assertEqual(self.check(fake_rawpy('0.27.1', False), False),
                         {'version': '0.27.1', 'openmp': False, 'xtrans_patch': False})
        with self.assertRaisesRegex(SystemExit, 'not the deterministic OpenMP build'):
            self.check(fake_rawpy('0.27.1', False), True)

    def test_patched_openmp_decoder_is_accepted(self):
        version = '0.27.1+' + rawpy_build.PATCHED_LABEL
        self.assertTrue(self.check(fake_rawpy(version, True), True)['xtrans_patch'])

    def test_patch_orders_xtrans_tiles_and_releases_progress_after_each_tile(self):
        text = (ROOT / 'packaging' / 'libraw-xtrans-deterministic-openmp.patch').read_text(encoding='utf-8')
        self.assertIn('+++ b/src/demosaic/xtrans_demosaic.cpp', text)
        self.assertIn('memory_order_acquire', text)
        self.assertIn('tiles_done[tile_row].store(tile_col + 1, std::memory_order_release);', text)
        self.assertIn('delete[] tiles_done;', text)
        # Half-size copies: one thread per image row keeps the serial write order.
        self.assertIn('+++ b/src/preprocessing/raw2image.cpp', text)
        self.assertIn('for (int imageRow = 0; imageRow < imageRows; imageRow++)', text)

    def test_patch_applies_to_the_pinned_rawpy_source_when_cached(self):
        sdist = ROOT / 'build' / 'rawpy-openmp' / f'rawpy-{rawpy_build.RAWPY_VERSION}.tar.gz'
        if not sdist.is_file():
            self.skipTest('rawpy sdist not cached; run scripts/build_rawpy_openmp.py')
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / sdist.name).write_bytes(sdist.read_bytes())
            source = rawpy_build.prepare_rawpy_source(work)
            demosaic = (source / 'external/LibRaw/src/demosaic/xtrans_demosaic.cpp').read_text(encoding='utf-8')
            self.assertEqual(demosaic.count('tiles_done'), 6)
            self.assertIn('rowsPerImageRow', (source / 'external/LibRaw/src/preprocessing/raw2image.cpp').read_text())
            self.assertIn(f'+{rawpy_build.PATCHED_LABEL}"', (source / 'rawpy/_version.py').read_text())


def exiftool_zip(path, extra=()):
    prefix = f'exiftool-{windows_build.EXIFTOOL_VERSION}_64/'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr(prefix + 'exiftool(-k).exe', b'MZ launcher')
        archive.writestr(prefix + 'README.txt', 'readme')
        archive.writestr(prefix + 'exiftool_files/LICENSE', 'license')
        archive.writestr(prefix + 'exiftool_files/lib/Image/ExifTool.pm', 'perl')
        archive.writestr(prefix + 'unrelated.txt', 'ignored')
        for name in extra:
            archive.writestr(name, 'x')


class WindowsPackagingTests(unittest.TestCase):
    def test_exiftool_is_installed_headless_beside_kora(self):
        with tempfile.TemporaryDirectory() as directory:
            archive, app = Path(directory) / 'exiftool.zip', Path(directory) / 'KŌRA app'
            exiftool_zip(archive)
            tools = windows_build.bundle_exiftool(app, archive)
            self.assertEqual((tools / 'exiftool.exe').read_bytes(), b'MZ launcher')
            self.assertFalse((tools / 'exiftool(-k).exe').exists())
            self.assertTrue((tools / 'exiftool_files/lib/Image/ExifTool.pm').is_file())
            self.assertFalse((tools / 'unrelated.txt').exists())

    def test_exiftool_archive_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'exiftool.zip'
            exiftool_zip(archive, [f'exiftool-{windows_build.EXIFTOOL_VERSION}_64/exiftool_files/../../escape.txt'])
            with self.assertRaisesRegex(SystemExit, 'Unexpected ExifTool archive entry'):
                windows_build.bundle_exiftool(Path(directory) / 'app', archive)
            self.assertFalse((Path(directory) / 'escape.txt').exists())

    def test_exiftool_archive_checksum_is_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'exiftool.zip'
            exiftool_zip(archive)
            with self.assertRaisesRegex(SystemExit, 'checksum mismatch'):
                windows_build.exiftool_archive(archive)
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            with patch.object(windows_build, 'EXIFTOOL_SHA256', digest):
                self.assertEqual(windows_build.exiftool_archive(archive), archive)

    def test_audit_requires_exiftool_and_openmp_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory)
            resources = app / '_internal'
            packaged_assets(resources)
            write_pe(app / 'Kora.exe')
            write_pe(resources / 'python313.dll')
            for module in ('rawpy', 'numpy', 'scipy', 'lensfunpy'):
                write_pe(resources / module / ('_' + module + '.pyd'))
            write_pe(resources / 'webview/lib/runtimes/win-x64/native/WebView2Loader.dll')
            for name in ('Microsoft.Web.WebView2.Core.dll', 'Microsoft.Web.WebView2.WinForms.dll'):
                write_pe(resources / 'webview/lib' / name, 0x14c)
            write_pe(resources / 'pythonnet/runtime/Python.Runtime.dll', 0x14c)
            problems = '\n'.join(audit_bundle(app)['problems'])
            self.assertIn('vcomp140.dll', problems)
            self.assertIn('exiftool', problems.lower())

    def test_installer_script_is_per_user_utf8_and_versioned(self):
        script = (ROOT / 'packaging' / 'KoraWindows.iss').read_bytes()
        self.assertTrue(script.startswith(b'\xef\xbb\xbf'))
        text = script.decode('utf-8-sig')
        self.assertIn('PrivilegesRequired=lowest', text)
        self.assertIn('OutputBaseFilename=Kora-{#AppVersion}-Windows-x64-Setup', text)
        self.assertIn('ArchitecturesAllowed=x64compatible', text)
        self.assertNotIn('PrivilegesRequiredOverridesAllowed', text)


if __name__ == '__main__':
    unittest.main()
