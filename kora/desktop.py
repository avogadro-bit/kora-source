"""Desktop entry point used by the packaged macOS and Windows applications."""
import argparse
import os
from pathlib import Path
import sys
from kora import diagnostics

from kora.compatibility import browser_disabled

# packaging/KoraWindows.iss names this mutex in AppMutex: while a KŌRA process
# holds it, the installer and uninstaller ask the user to close KŌRA first.
WINDOWS_APP_MUTEX = 'Kora-6E1F7B52-3C4D-4E0B-9A71-4B6D2C1F0A55'
_windows_app_mutex = None


def hold_windows_app_mutex():
    """Keep the mutex open until the process exits; Windows then closes it."""
    global _windows_app_mutex
    import ctypes
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
    # A failure only loses the uninstall guard; KŌRA must still start.
    _windows_app_mutex = kernel32.CreateMutexW(None, False, WINDOWS_APP_MUTEX)
    return _windows_app_mutex


def serve(*args, **kwargs):
    # Native-library import failures must reach the startup handler as well.
    from kora.gui import serve as serve_gui
    return serve_gui(*args, **kwargs)


def show_macos_startup_error():
    from AppKit import NSAlert, NSApplication, NSApplicationActivationPolicyRegular
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    app.activateIgnoringOtherApps_(True)
    alert = NSAlert.alloc().init()
    alert.setMessageText_('KŌRA could not start')
    alert.setInformativeText_(
        'The application could not open its window. '
        'Please share this diagnostic file when reporting the problem:\n\n' + str(log_path()))
    alert.addButtonWithTitle_('Close')
    alert.runModal()


def log_path():
    return diagnostics.log_path()


def record_crash(exc):
    """Keep frozen-app startup failures diagnosable when no terminal is visible."""
    diagnostics.record_error('startup', exc, path=log_path())


def main(argv=None):
    diagnostics.install_hooks()
    parser = argparse.ArgumentParser(description="KŌRA desktop application")
    parser.add_argument("--root", type=Path, action="append", default=[])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--smoke-report", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        # Headless runs too: any Kora.exe process keeps the installed files open.
        hold_windows_app_mutex()
    open_browser = False
    try:
        open_browser = not args.no_browser and not browser_disabled()
        if sys.platform == "win32" and open_browser:
            from kora.windows_app import run
            if args.smoke_report:
                return run(args.root, args.port, smoke_report=args.smoke_report)
            return run(args.root, args.port)
        if sys.platform == "darwin" and getattr(sys, "frozen", False) and open_browser:
            from kora.macos_app import run
            return run(args.root, args.port)
        serve(
            args.root,
            args.port,
            open_browser=open_browser,
        )
        return 0
    except Exception as exc:
        record_crash(exc)
        if sys.platform == "win32" and not args.no_browser and not args.smoke_report:
            from kora.windows_app import show_startup_error
            show_startup_error()
        elif sys.platform == 'darwin' and open_browser and getattr(sys, 'frozen', False):
            try:
                show_macos_startup_error()
            except Exception as alert_error:
                diagnostics.record_error('startup-alert', alert_error)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
