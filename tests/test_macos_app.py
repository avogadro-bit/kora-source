"""Native lifecycle checks without launching a real window in the unit suite."""
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from kora import macos_app


class MacLifecycleTests(unittest.TestCase):
    def run_window(self, start_error=None):
        stopped = threading.Event()
        server = Mock()
        server.shutdown.side_effect = stopped.set
        window = Mock()
        webview = SimpleNamespace(settings={}, create_window=Mock(return_value=window),
                                  start=Mock(side_effect=start_error))

        def serve(roots, port, on_ready):
            on_ready(server, 'http://127.0.0.1:8877/#session=test')
            stopped.wait(5)

        with tempfile.TemporaryDirectory() as directory, \
                patch.dict('sys.modules', {'webview': webview}), \
                patch.object(macos_app, 'serve', side_effect=serve), \
                patch.object(macos_app.Path, 'home', return_value=Path(directory)):
            if start_error:
                with self.assertRaisesRegex(RuntimeError, 'window failed'):
                    macos_app.run([], 8877)
            else:
                self.assertEqual(macos_app.run([], 8877), 0)
        server.shutdown.assert_called_once()
        return webview

    def test_native_window_starts_fullscreen_with_downloads(self):
        webview = self.run_window()
        options = webview.create_window.call_args.kwargs
        self.assertTrue(options['fullscreen'])
        self.assertEqual(options['min_size'], (820, 600))
        self.assertTrue(webview.settings['ALLOW_DOWNLOADS'])
        self.assertFalse(webview.settings['ALLOW_FILE_URLS'])
        self.assertFalse(webview.start.call_args.kwargs['private_mode'])
        self.assertEqual(webview.start.call_args.kwargs['gui'], 'cocoa')

    def test_window_failure_stops_server(self):
        self.run_window(RuntimeError('window failed'))

    def test_server_failure_propagates_without_opening_window(self):
        webview = Mock()
        with patch.dict('sys.modules', {'webview': webview}), \
                patch.object(macos_app, 'serve', side_effect=ValueError('bad port')):
            with self.assertRaisesRegex(ValueError, 'bad port'):
                macos_app.run([], 0)
        webview.create_window.assert_not_called()

    def test_toggle_dispatches_native_action_on_main_thread(self):
        controls = macos_app.WindowControls()
        controls._window = Mock()
        helper = Mock()
        with patch.dict('sys.modules', {'PyObjCTools': SimpleNamespace(AppHelper=helper)}):
            controls.toggle_fullscreen()
        helper.callAfter.assert_called_once_with(controls._window.native.toggleFullScreen_, None)

    def test_stalled_startup_times_out_and_rejects_late_server(self):
        release = threading.Event()
        finished = threading.Event()
        webview = Mock()
        rejected = []

        def serve(roots, port, on_ready):
            release.wait(5)
            try:
                on_ready(Mock(), 'http://127.0.0.1:8877/')
            except TimeoutError:
                rejected.append(True)
                raise
            finally:
                finished.set()

        with patch.dict('sys.modules', {'webview': webview}), \
                patch.object(macos_app, 'serve', side_effect=serve), \
                patch.object(macos_app, 'record_error'), \
                patch.object(macos_app, 'STARTUP_TIMEOUT', 0.01):
            try:
                with self.assertRaisesRegex(TimeoutError, 'did not start'):
                    macos_app.run([], 8877)
            finally:
                release.set()
                self.assertTrue(finished.wait(2))
        self.assertEqual(rejected, [True])
        webview.create_window.assert_not_called()

    def test_worker_exit_before_ready_is_reported(self):
        with patch.dict('sys.modules', {'webview': Mock()}), \
                patch.object(macos_app, 'serve'), patch.object(macos_app, 'record_error'):
            with self.assertRaisesRegex(RuntimeError, 'stopped before it was ready'):
                macos_app.run([], 8877)
