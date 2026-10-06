"""Native, fullscreen macOS studio with an isolated local HTTP worker."""
import threading
from pathlib import Path

from .gui import serve
from .diagnostics import record_error
from .compatibility import mac_webview_directory

STARTUP_TIMEOUT = 30


class WindowControls:
    """Window-only control called through the session-authenticated HTTP API."""

    def __init__(self):
        self._window = None

    def toggle_fullscreen(self):
        # Use actual Cocoa state: the green button and Control-Command-F work too.
        from PyObjCTools import AppHelper
        if self._window is not None and self._window.native is not None:
            AppHelper.callAfter(self._window.native.toggleFullScreen_, None)


def run(roots, port):
    import webview

    ready = threading.Event()
    state_lock = threading.Lock()
    state = {}
    controls = WindowControls()

    def on_ready(server, url):
        with state_lock:
            if state.get('cancelled'):
                # serve() closes its socket when this callback raises.
                raise TimeoutError('Application startup was cancelled')
            server.toggle_fullscreen = controls.toggle_fullscreen
            state.update(server=server, url=url)
            ready.set()

    def worker():
        try:
            serve(roots, port, on_ready=on_ready)
            if not ready.is_set():
                raise RuntimeError('Local service stopped before it was ready')
        except Exception as exc:
            record_error('native-server-worker', exc)
            with state_lock:
                state['error'] = exc
                ready.set()

    thread = threading.Thread(target=worker, name="KoraServer", daemon=True)
    thread.start()
    ready.wait(STARTUP_TIMEOUT)
    with state_lock:
        if not ready.is_set():
            state['cancelled'] = True
            raise TimeoutError('The local service did not start within 30 seconds')
        if 'error' in state:
            raise state['error']
    try:
        webview.settings['ALLOW_DOWNLOADS'] = True
        webview.settings['ALLOW_FILE_URLS'] = False
        controls._window = webview.create_window(
            "KŌRA", state['url'],
            width=1440, height=900, min_size=(820, 600), fullscreen=True,
            background_color='#0d100f',
        )
        storage = mac_webview_directory()
        storage.mkdir(parents=True, exist_ok=True)
        webview.start(gui='cocoa', private_mode=False, storage_path=str(storage))
    finally:
        state['server'].shutdown()
        thread.join(timeout=3)
    return 0
