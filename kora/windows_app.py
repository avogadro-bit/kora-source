"""Windows desktop shell using WebView2; rendering stays in the shared engine."""
import ctypes
import json
from pathlib import Path
import threading
import time

from .diagnostics import record_error
from .gui import serve
from .platform_support import windows_data_directory as data_directory

STARTUP_TIMEOUT = 30


class WindowControls:
    def __init__(self):
        self.window = None

    def toggle_fullscreen(self):
        if self.window is not None:
            self.window.toggle_fullscreen()


def run(roots, port, smoke_report=None):
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
            record_error('windows-server-worker', exc)
            with state_lock:
                state['error'] = exc
                ready.set()

    thread = threading.Thread(target=worker, name='KoraServer', daemon=True)
    thread.start()
    ready.wait(STARTUP_TIMEOUT)
    with state_lock:
        if not ready.is_set():
            state['cancelled'] = True
            raise TimeoutError('The local service did not start within 30 seconds')
        if 'error' in state:
            raise state['error']
    try:
        storage = data_directory() / 'WebView'
        storage.mkdir(parents=True, exist_ok=True)
        webview.settings['ALLOW_DOWNLOADS'] = True
        webview.settings['ALLOW_FILE_URLS'] = False
        controls.window = webview.create_window(
            'KŌRA', state['url'], width=1440, height=900,
            min_size=(820, 600), fullscreen=True, background_color='#0d100f',
        )
        # Never fall back to the obsolete Internet Explorer renderer.
        def smoke_check():
            try:
                from .studio import studio_status
                status = studio_status()
                expected_films = sorted(set(status['official_lut_films']) |
                                        set(status['xm5_reference_validation']['films']))
                window = controls.window
                if not window.events.loaded.wait(30):
                    raise RuntimeError('WebView2 page did not load')
                result = {}
                for _ in range(100):
                    result = window.evaluate_js("({title:document.title, films:Array.from(document.querySelector('#film').options, o=>o.value).sort(), grid:!!document.querySelector('#wb-grid')})")
                    if result and result.get('films') == expected_films:
                        break
                    time.sleep(.1)
                if result.get('title') != 'KŌRA' or result.get('films') != expected_films or not result.get('grid'):
                    raise RuntimeError(f'Unexpected Windows UI state: {result}')
                from .windows_smoke import check_raw
                raw_result = check_raw(state['server'], roots)
                if raw_result is not None:
                    result['raw'] = raw_result
                Path(smoke_report).write_text(json.dumps(result), encoding='utf-8')
            except Exception as exc:
                state['error'] = exc
                record_error('windows-ui-smoke', exc)
            finally:
                controls.window.destroy()

        webview.start(func=smoke_check if smoke_report else None, gui='edgechromium',
                      private_mode=False, storage_path=str(storage))
    finally:
        state['server'].shutdown()
        thread.join(timeout=3)
    if 'error' in state:
        raise state['error']
    return 0


def show_startup_error():
    ctypes.windll.user32.MessageBoxW(
        None, 'KŌRA could not start. Details were saved in:\n'
        f'{data_directory() / "Logs" / "errors.jsonl"}\n\n'
        'KŌRA requires Microsoft Edge WebView2 Runtime and .NET Framework 4.8. '
        'If either is missing, install it and try again.', 'KŌRA', 0x10,
    )
