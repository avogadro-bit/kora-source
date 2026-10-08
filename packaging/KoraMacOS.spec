# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files
from kora import __version__
from kora.compatibility import MAC_BUNDLE_ID


project_root = Path(SPEC).resolve().parent.parent
datas = collect_data_files(
    "kora",
    includes=["film_data/*", "static/*", "luts/*.json", "lensfun_db/*"],
)
datas += [
    (str(project_root / "LICENSE"), "."),
    (str(project_root / "THIRD_PARTY.md"), "."),
]
notices = project_root / "build" / "release-notices"
if not (notices / "inventory.json").is_file():
    raise RuntimeError("Run scripts/prepare_release_notices.py before packaging")
datas.append((str(notices), "Third-Party-Notices"))
datas += collect_data_files("webview")

a = Analysis(
    [str(project_root / "kora" / "desktop.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=["webview.platforms.cocoa"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["capstone", "unicorn"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Kora",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Kora",
)
app = BUNDLE(
    coll,
    name="KŌRA.app",
    icon=str(project_root / "build" / "AppIcon.icns"),
    bundle_identifier=MAC_BUNDLE_ID,
    version=__version__,
    info_plist={
        "CFBundleDisplayName": "KŌRA",
        "CFBundleName": "KŌRA",
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        "LSMinimumSystemVersion": "14.0",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "Copyright © 2026 Paul Wellenreiter",
    },
)
