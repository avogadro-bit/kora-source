# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPEC).resolve().parent.parent
notices = root / 'build' / 'release-notices'
if not (notices / 'inventory.json').is_file():
    raise RuntimeError('Run scripts/prepare_release_notices.py first')
datas = collect_data_files('kora', includes=['static/*', 'luts/*.json', 'lensfun_db/*'])
datas += collect_data_files('webview')
datas += [(str(root / 'LICENSE'), '.'), (str(root / 'THIRD_PARTY.md'), '.'),
          (str(notices), 'Third-Party-Notices')]
a = Analysis([str(root / 'kora' / 'desktop.py')], pathex=[str(root)],
             binaries=[], datas=datas, hiddenimports=['webview.platforms.winforms', 'webview.platforms.edgechromium'],
             hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['capstone', 'unicorn', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'tkinter'],
             noarchive=False, optimize=1)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Kora',
          icon=str(root / 'build' / 'Kora.ico'), debug=False, strip=False,
          upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Kora')
