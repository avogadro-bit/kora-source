from pathlib import Path
import hashlib
import os
import shutil
import sys
import tarfile
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

from scripts import build_rawpy_openmp as rawpy_build
from scripts import build_windows_release as windows_build
from scripts import windows_manifest
from scripts.audit_windows_bundle import audit_bundle, pe_machine
from tests.test_portability import packaged_assets, windows_app, write_pe

ROOT = Path(__file__).resolve().parents[1]
# Manifest of the exiftool(-k).exe launcher in ExifTool 13.59's Windows package.
EXIFTOOL_MANIFEST = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
<application xmlns="urn:schemas-microsoft-com:asm.v3">
    <windowsSettings xmlns:ws2="http://schemas.microsoft.com/SMI/2016/WindowsSettings">
        <ws2:longPathAware>true</ws2:longPathAware>
    </windowsSettings>
</application>
</assembly>
'''
# Settings the ExifTool launcher does not have, as in python.exe's manifest.
SECURITY_MANIFEST = EXIFTOOL_MANIFEST.replace(b'<application', b'''<trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
<security><requestedPrivileges><requestedExecutionLevel level="asInvoker"/></requestedPrivileges></security>
</trustInfo>
<application''', 1)


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
            with patch.object(windows_build, 'embed_utf8_manifest') as embed:
                tools = windows_build.bundle_exiftool(app, archive)
            embed.assert_called_once_with(tools / 'exiftool.exe')
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

    def test_utf8_manifest_sets_the_code_page_and_keeps_long_paths(self):
        manifest = windows_manifest.UTF8_MANIFEST
        self.assertTrue(windows_manifest.has_utf8_code_page(manifest))
        self.assertIn(b'<longPathAware xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">true<', manifest)
        self.assertFalse(windows_manifest.has_utf8_code_page(EXIFTOOL_MANIFEST))
        # Windows reads activeCodePage only under application/windowsSettings.
        misplaced = (b'<assembly xmlns="urn:schemas-microsoft-com:asm.v1"><activeCodePage '
                     b'xmlns="http://schemas.microsoft.com/SMI/2019/WindowsSettings">UTF-8</activeCodePage></assembly>')
        for other in (misplaced, manifest.replace(b'>UTF-8<', b'>Legacy<'), b'<assembly', None):
            self.assertFalse(windows_manifest.has_utf8_code_page(other), other)

    def test_utf8_manifest_replaces_the_exiftool_manifest_only(self):
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory) / 'KŌRA' / 'exiftool.exe'
            write_pe(exe, manifest=EXIFTOOL_MANIFEST)
            self.assertEqual(windows_manifest.manifest_resources(exe), [(1033, EXIFTOOL_MANIFEST)])
            rewrite = lambda path, manifest, language: write_pe(path, manifest=manifest)
            with patch.object(windows_manifest, 'replace_manifest', side_effect=rewrite) as replace:
                self.assertEqual(windows_manifest.embed_utf8_manifest(exe), 1033)
            replace.assert_called_once_with(exe, windows_manifest.UTF8_MANIFEST, 1033)
            self.assertEqual(windows_manifest.read_manifest(exe), windows_manifest.UTF8_MANIFEST)
            # A launcher from another ExifTool package could declare more settings.
            write_pe(exe, manifest=SECURITY_MANIFEST)
            with patch.object(windows_manifest, 'replace_manifest') as replace, \
                    self.assertRaisesRegex(SystemExit, 'would drop.*trustInfo'):
                windows_manifest.embed_utf8_manifest(exe)
            replace.assert_not_called()
            write_pe(exe)
            with self.assertRaisesRegex(ValueError, 'Invalid PE resources'):
                windows_manifest.embed_utf8_manifest(exe)

    @unittest.skipUnless(sys.platform == 'win32', 'uses the Windows resource update API')
    def test_utf8_manifest_is_written_into_a_real_windows_executable(self):
        # Antivirus scanners can hold the new executable open for a moment.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            exe = Path(directory) / 'KŌRA' / 'launcher.exe'
            exe.parent.mkdir()
            shutil.copyfile(sys.executable, exe)
            machine = pe_machine(exe)
            with self.assertRaisesRegex(SystemExit, 'would drop'):
                windows_manifest.embed_utf8_manifest(exe)
            language = windows_manifest.manifest_resources(exe)[0][0]
            windows_manifest.replace_manifest(exe, EXIFTOOL_MANIFEST, language)
            self.assertEqual(windows_manifest.read_manifest(exe), EXIFTOOL_MANIFEST)
            self.assertEqual(windows_manifest.embed_utf8_manifest(exe), language)
            self.assertEqual(windows_manifest.manifest_resources(exe), [(language, windows_manifest.UTF8_MANIFEST)])
            self.assertEqual(pe_machine(exe), machine)

    def test_audit_requires_utf8_code_page_for_exiftool(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory)
            windows_app(app)
            self.assertTrue(audit_bundle(app)['compatible'])
            write_pe(app / 'tools/exiftool.exe', manifest=EXIFTOOL_MANIFEST)
            self.assertEqual(audit_bundle(app)['problems'],
                             ['tools/exiftool.exe lacks the activeCodePage UTF-8 manifest'])

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

    def test_audit_requires_x64_cpp_runtime_at_bundle_root(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory)
            resources = windows_app(app)
            self.assertTrue(audit_bundle(app)['compatible'])
            # A Windows on Arm build leaves only numpy's renamed private copy.
            (resources / 'MSVCP140.dll').unlink()
            write_pe(resources / 'numpy.libs/msvcp140-a4c2229bdc2a2a630acdc095b4d86008.dll')
            write_pe(resources / 'rawpy/msvcp140.dll')
            problems = audit_bundle(app)['problems']
            self.assertEqual(problems, ['Missing Visual C++ runtime: _internal/MSVCP140.dll'])
            write_pe(resources / 'msvcp140.dll', 0xaa64)
            problems = audit_bundle(app)['problems']
            self.assertEqual(len(problems), 1)
            self.assertIn('msvcp140.dll is arm64; expected x64', problems[0])

    def test_vc_redist_is_newest_visual_studio_x64_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vswhere = root / 'x86' / 'Microsoft Visual Studio' / 'Installer' / 'vswhere.exe'
            vswhere.parent.mkdir(parents=True)
            vswhere.write_bytes(b'')
            installs = [root / 'VS 2022' / 'BuildTools', root / 'VS 2022' / 'Community']
            for install, version in ((installs[0], '14.44.35112'), (installs[1], '14.9.30000'),
                                     (installs[1], 'v143')):
                write_pe(install / 'VC/Redist/MSVC' / version / 'x64/Microsoft.VC143.CRT/msvcp140.dll')
            write_pe(installs[1] / 'VC/Redist/MSVC/14.50.1/onecore/x64/Microsoft.VC143.CRT/msvcp140.dll')
            result = types.SimpleNamespace(stdout=''.join(f'{path}\r\n' for path in installs))
            with patch.dict(os.environ, {'ProgramFiles(x86)': str(root / 'x86')}), \
                    patch.object(windows_build.subprocess, 'run', return_value=result) as run:
                self.assertEqual(windows_build.vc_redist_x64(),
                                 installs[0] / 'VC/Redist/MSVC/14.44.35112/x64/Microsoft.VC143.CRT')
            self.assertEqual(run.call_args.args[0][:5], [str(vswhere), '-all', '-products', '*', '-property'])
            with patch.dict(os.environ, {'ProgramFiles(x86)': str(root / 'none')}):
                self.assertIsNone(windows_build.vc_redist_x64())

    def test_build_fills_missing_or_foreign_cpp_runtime_from_redist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = windows_app(root / 'app')
            redist = root / 'Microsoft.VC143.CRT'
            for name in ('msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'):
                write_pe(redist / name)
                (redist / name).write_bytes((redist / name).read_bytes() + b'redist')
            with patch.object(windows_build, 'vc_redist_x64') as find:
                self.assertEqual(windows_build.bundle_vc_runtime(root / 'app'), [])
            find.assert_not_called()
            (resources / 'MSVCP140.dll').unlink()
            write_pe(resources / 'VCRUNTIME140_1.dll', 0xaa64)
            with patch.object(windows_build, 'vc_redist_x64', return_value=None), \
                    self.assertRaisesRegex(SystemExit, 'MSVCP140.dll, VCRUNTIME140_1.dll.*redistributable'):
                windows_build.bundle_vc_runtime(root / 'app')
            with patch.object(windows_build, 'vc_redist_x64', return_value=redist):
                self.assertEqual(windows_build.bundle_vc_runtime(root / 'app'), ['MSVCP140.dll', 'VCRUNTIME140_1.dll'])
            for name, copied in (('MSVCP140.dll', True), ('VCRUNTIME140.dll', False), ('VCRUNTIME140_1.dll', True)):
                self.assertEqual((resources / name).read_bytes().endswith(b'redist'), copied, name)
            self.assertTrue(audit_bundle(root / 'app')['compatible'])

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
