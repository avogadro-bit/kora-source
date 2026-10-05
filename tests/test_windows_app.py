import io
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from kora import windows_app, platform_support, desktop, diagnostics, official_luts, raw, gui


class WindowsLifecycleTests(unittest.TestCase):
    def test_legacy_console_encoding_does_not_prevent_server_startup(self):
        server = Mock(server_port=8765)
        ready = Mock()
        with io.TextIOWrapper(io.BytesIO(), encoding='cp1252') as output, \
                patch('sys.stdout', output), patch.object(gui, 'install_hooks'), \
                patch.object(gui, 'bind_studio_server', return_value=server), \
                patch.object(gui, 'Library'):
            gui.serve([], on_ready=ready)
        ready.assert_called_once()
        server.serve_forever.assert_called_once()
        server.server_close.assert_called_once()

    def run_window(self, failure=None):
        stopped = threading.Event()
        server = Mock()
        server.shutdown.side_effect = stopped.set
        webview = SimpleNamespace(settings={}, create_window=Mock(return_value=Mock()), start=Mock(side_effect=failure))

        def serve(roots, port, on_ready):
            on_ready(server, 'http://127.0.0.1:8877/#session=test')
            stopped.wait(5)

        with tempfile.TemporaryDirectory() as directory, patch.dict('sys.modules', {'webview': webview}), \
                patch.object(windows_app, 'serve', side_effect=serve), \
                patch.object(windows_app, 'data_directory', return_value=Path(directory)):
            if failure:
                with self.assertRaisesRegex(RuntimeError, 'window failed'):
                    windows_app.run([], 8877)
            else:
                self.assertEqual(windows_app.run([], 8877), 0)
        server.shutdown.assert_called_once()
        return webview

    def test_fullscreen_edgechromium_persistent_storage_and_downloads(self):
        view = self.run_window()
        self.assertTrue(view.create_window.call_args.kwargs['fullscreen'])
        self.assertEqual(view.start.call_args.kwargs['gui'], 'edgechromium')
        self.assertFalse(view.start.call_args.kwargs['private_mode'])
        self.assertTrue(view.settings['ALLOW_DOWNLOADS'])
        self.assertFalse(view.settings['ALLOW_FILE_URLS'])

    def test_window_failure_stops_server(self):
        self.run_window(RuntimeError('window failed'))

    def test_server_failure_does_not_open_window(self):
        view = Mock()
        with patch.dict('sys.modules', {'webview': view}), patch.object(windows_app, 'serve', side_effect=ValueError('bad port')):
            with self.assertRaisesRegex(ValueError, 'bad port'):
                windows_app.run([], 0)
        view.create_window.assert_not_called()

    def test_fullscreen_control(self):
        controls = windows_app.WindowControls()
        controls.window = Mock()
        controls.toggle_fullscreen()
        controls.window.toggle_fullscreen.assert_called_once()

    def test_desktop_routes_windows_to_native_shell(self):
        with patch.object(desktop.sys, 'platform', 'win32'), patch.object(windows_app, 'run', return_value=0) as run, \
                patch.object(desktop, 'serve') as serve, patch.object(desktop.diagnostics, 'install_hooks'):
            self.assertEqual(desktop.main(['--port', '8877']), 0)
        run.assert_called_once_with([], 8877)
        serve.assert_not_called()

    def test_windows_data_paths(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {'LOCALAPPDATA': directory}), \
                patch.object(platform_support.sys, 'platform', 'win32'):
            self.assertEqual(platform_support.windows_data_directory(), Path(directory) / 'Kora')
            self.assertEqual(diagnostics.log_path(), Path(directory) / 'Kora/Logs/errors.jsonl')
            with patch.dict('os.environ', {}, clear=True):
                with patch('kora.official_luts.windows_data_directory', return_value=Path(directory) / 'Kora'):
                    self.assertEqual(official_luts.user_lut_directory(), Path(directory) / 'Kora/luts')

    def test_windows_cloud_placeholders_are_not_read(self):
        path = Mock()
        for flag in (0x1000, 0x40000, 0x400000):
            path.stat.return_value = SimpleNamespace(st_file_attributes=flag, st_size=100, st_blocks=1)
            self.assertFalse(raw.local_file(path))
        path.stat.return_value = SimpleNamespace(st_file_attributes=0, st_size=100, st_blocks=1)
        self.assertTrue(raw.local_file(path))

    def test_windows_memory_and_drive_detection(self):
        kernel = Mock()
        def memory(pointer):
            pointer._obj.total_physical = 32 * 1024**3
            return 1
        kernel.GlobalMemoryStatusEx.side_effect = memory
        kernel.GetLogicalDrives.return_value = (1 << 2) | (1 << 3)
        with patch.object(platform_support.sys, 'platform', 'win32'), \
                patch.object(platform_support.ctypes, 'windll', SimpleNamespace(kernel32=kernel), create=True):
            self.assertEqual(platform_support.physical_memory_bytes(), 32 * 1024**3)
            self.assertEqual(platform_support.drive_roots(), [Path('C:/'), Path('D:/')])
