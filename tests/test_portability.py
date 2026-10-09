import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts.audit_package_assets import audit_assets
from scripts.audit_windows_bundle import audit_bundle, pe_machine
from scripts.release_paths import release_paths


def write_pe(path, machine=0x8664):
    path.parent.mkdir(parents=True, exist_ok=True)
    header = bytearray(70)
    header[:2] = b'MZ'
    struct.pack_into('<I', header, 60, 64)
    header[64:68] = b'PE\0\0'
    struct.pack_into('<H', header, 68, machine)
    path.write_bytes(header)


def packaged_assets(resources):
    for name in ('kora/static/index.html', 'kora/static/app.js', 'kora/static/style.css',
                 'kora/static/kora.css', 'kora/static/diagnostics.js', 'kora/static/viewer.js',
                 'kora/lensfun_db/origin.json', 'kora/lensfun_db/camera.xml',
                 'kora/film_data/NOTICE.txt', 'Third-Party-Notices/inventory.json'):
        path = resources / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('test asset', encoding='utf-8')
    data = b'example profile data'
    (resources / 'kora/film_data/kodachrome64_v1.npz').write_bytes(data)
    (resources / 'kora/film_data/kodachrome64_v1.json').write_text(
        json.dumps({'sha256': hashlib.sha256(data).hexdigest()}), encoding='utf-8')


class PortabilityTests(unittest.TestCase):
    def test_windows_smoke_stops_only_its_live_process_tree(self):
        from scripts import smoke_windows_release as smoke
        process = Mock(pid=1234)
        process.poll.return_value = None
        with patch.object(smoke.sys, 'platform', 'win32'), \
                patch.object(smoke.subprocess, 'run', return_value=Mock(returncode=0)) as run:
            smoke.stop_process(process)
        self.assertEqual(run.call_args.args[0], ['taskkill', '/PID', '1234', '/T', '/F'])
        process.wait.assert_called_once_with(timeout=15)
        process.terminate.assert_not_called()

    def test_windows_smoke_cleanup_does_not_replace_original_failure(self):
        from scripts import smoke_windows_release as smoke
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / 'smoke'
            workspace.mkdir()
            with patch.object(smoke.tempfile, 'mkdtemp', return_value=str(workspace)), \
                    patch.object(smoke.shutil, 'rmtree', side_effect=PermissionError('locked')), \
                    patch.object(smoke.time, 'sleep'):
                with self.assertRaisesRegex(RuntimeError, 'original TLS error') as caught:
                    with smoke.smoke_workspace():
                        raise RuntimeError('original TLS error')
            self.assertIn('temporary smoke folder', caught.exception.__notes__[0])

    def test_windows_builder_uses_interpreter_architecture_on_arm_host(self):
        from scripts import build_windows_release as builder
        with patch.object(builder.sys, 'platform', 'win32'), \
                patch.object(builder.sysconfig, 'get_platform', return_value='win-amd64'), \
                patch.object(builder.struct, 'calcsize', return_value=8), \
                patch('platform.machine', return_value='ARM64'):
            self.assertTrue(builder.windows_x64_python())
            with patch.object(builder.sysconfig, 'get_platform', return_value='win-arm64'):
                self.assertFalse(builder.windows_x64_python())
            with patch.object(builder.struct, 'calcsize', return_value=4):
                self.assertFalse(builder.windows_x64_python())

    def test_architecture_specific_builds_do_not_erase_each_other(self):
        with patch.dict(os.environ, {'KORA_BUILD_VARIANT': 'x86_64'}):
            intel = release_paths(Path('/project'))
        with patch.dict(os.environ, {'KORA_BUILD_VARIANT': 'arm64'}):
            arm = release_paths(Path('/project'))
        self.assertTrue(set(intel).isdisjoint(arm))
        self.assertEqual(intel, (Path('/project/build/x86_64'),
                               Path('/project/dist/macos-x86_64'), Path('/project/dist/release-x86_64')))
        with patch.dict(os.environ, {'KORA_BUILD_VARIANT': '../'}):
            with self.assertRaises(ValueError):
                release_paths('/project')

    def test_assets_checked_in_moved_unicode_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            resources = Path(directory) / 'KŌRA été 日本' / '_internal'
            packaged_assets(resources)
            self.assertTrue(audit_assets(resources)['compatible'])
            table = resources / 'kora/film_data/kodachrome64_v1.npz'
            table.write_bytes(b'corrupt table')
            report = audit_assets(resources)
            self.assertFalse(report['compatible'])
            self.assertIn('checksum', '\n'.join(report['problems']))

    def test_missing_model_and_lens_database_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            report = audit_assets(directory)
            self.assertFalse(report['compatible'])
            self.assertIn('kodachrome64_v1.npz', '\n'.join(report['problems']))
            self.assertIn('lens correction', '\n'.join(report['problems']))

    def test_pe_architecture_and_truncated_header(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.pyd'
            for machine, label in ((0x8664, 'x64'), (0xaa64, 'arm64'), (0x14c, 'x86')):
                write_pe(path, machine)
                self.assertEqual(pe_machine(path), label)
            path.write_bytes(b'MZ')
            with self.assertRaises(ValueError):
                pe_machine(path)

    def test_windows_bundle_rejects_wrong_native_architecture_but_accepts_managed_dlls(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory)
            resources = app / '_internal'
            packaged_assets(resources)
            write_pe(app / 'Kora.exe')
            write_pe(resources / 'python313.dll')
            for module in ('rawpy', 'numpy', 'scipy', 'lensfunpy'):
                write_pe(resources / module / ('_' + module + '.pyd'))
            loader = resources / 'webview/lib/runtimes/win-x64/native/WebView2Loader.dll'
            write_pe(loader)
            for name in ('Microsoft.Web.WebView2.Core.dll', 'Microsoft.Web.WebView2.WinForms.dll'):
                write_pe(resources / 'webview/lib' / name, 0x14c)
            write_pe(resources / 'pythonnet/runtime/Python.Runtime.dll', 0x14c)
            self.assertTrue(audit_bundle(app)['compatible'])
            write_pe(loader, 0xaa64)
            report = audit_bundle(app)
            self.assertFalse(report['compatible'])
            self.assertIn('is arm64; expected x64', '\n'.join(report['problems']))

    def test_windows_smoke_expects_all_current_films(self):
        from kora.windows_app import expected_films
        from kora.studio import studio_status
        films = expected_films(studio_status())
        self.assertIn('kodachrome64', films)
        self.assertIn('provia', films)
        self.assertIn('nostalgic_negative', films)
        self.assertEqual(len(films), len(set(films)))
