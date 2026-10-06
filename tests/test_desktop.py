import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from kora import desktop


class DesktopTests(unittest.TestCase):
    def test_frozen_macos_uses_native_lifecycle(self):
        from unittest.mock import Mock
        run = Mock(return_value=0)
        with patch.object(desktop.sys, "frozen", True, create=True), \
             patch.object(desktop.sys, "platform", "darwin"), \
             patch.dict("sys.modules", {"kora.macos_app": SimpleNamespace(run=run)}), \
             patch("kora.desktop.serve") as serve:
            self.assertEqual(desktop.main(["--port", "8877"]), 0)
            run.assert_called_once_with([], 8877)
            serve.assert_not_called()

    def test_frozen_headless_bypasses_native_lifecycle(self):
        with patch.object(desktop.sys, "frozen", True, create=True), \
             patch.object(desktop.sys, "platform", "darwin"), \
             patch("kora.desktop.serve") as serve:
            self.assertEqual(desktop.main(["--no-browser"]), 0)
            serve.assert_called_once_with([], 8765, open_browser=False)

    def test_desktop_entry_opens_browser_by_default(self):
        with patch.object(desktop.sys, 'platform', 'linux'), patch("kora.desktop.serve") as serve:
            self.assertEqual(desktop.main(["--port", "8877"]), 0)
        serve.assert_called_once_with([], 8877, open_browser=True)

    def test_desktop_entry_supports_headless_release_check(self):
        with patch("kora.desktop.serve") as serve:
            self.assertEqual(desktop.main(["--no-browser", "--root", "/tmp/photos"]), 0)
        serve.assert_called_once_with([Path("/tmp/photos")], 8765, open_browser=False)

    def test_startup_failure_is_logged(self):
        with tempfile.TemporaryDirectory() as root, \
             patch("kora.desktop.serve", side_effect=RuntimeError("boom")), \
             patch("kora.desktop.log_path", return_value=Path(root) / "app.log"):
            self.assertEqual(desktop.main(["--no-browser"]), 2)
            self.assertIn("RuntimeError: boom", (Path(root) / "app.log").read_text())

    def test_native_startup_failure_shows_mac_alert(self):
        with patch.object(desktop.sys, 'frozen', True, create=True), \
                patch.object(desktop.sys, 'platform', 'darwin'), \
                patch.dict('sys.modules', {'kora.macos_app': SimpleNamespace(
                    run=lambda *_: (_ for _ in ()).throw(ImportError('native library failed')))}), \
                patch.object(desktop, 'record_crash') as record, \
                patch.object(desktop, 'show_macos_startup_error') as alert:
            self.assertEqual(desktop.main([]), 2)
        record.assert_called_once()
        alert.assert_called_once()

    def test_headless_failure_does_not_show_mac_alert(self):
        with patch.object(desktop.sys, 'frozen', True, create=True), \
                patch.object(desktop.sys, 'platform', 'darwin'), \
                patch.object(desktop, 'serve', side_effect=ImportError('native library failed')), \
                patch.object(desktop, 'record_crash'), \
                patch.object(desktop, 'show_macos_startup_error') as alert:
            self.assertEqual(desktop.main(['--no-browser']), 2)
        alert.assert_not_called()
