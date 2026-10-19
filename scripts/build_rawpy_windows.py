"""Build the deterministic OpenMP rawpy wheel for Windows x64.

PyPI's Windows rawpy wheel already enables OpenMP (vcomp140.dll), so its
X-Trans demosaic varies between runs. This script follows rawpy v0.27.1's
own Windows CI (.github/scripts/build-windows.ps1): Visual Studio x64 tools,
vcpkg 2026.07.29 static zlib, libjpeg-turbo[jpeg8], JasPer and Little CMS, then
`pip wheel`. It adds packaging/libraw-xtrans-deterministic-openmp.patch and the
patched version label. The wheel is written to build/wheels/; nothing is published.

    python scripts/build_rawpy_windows.py
"""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_rawpy_openmp import PATCHED_LABEL, ROOT, WHEELS, prepare_rawpy_source, run  # noqa: E402

WORK = ROOT/'build'/'rawpy-windows'
VCPKG_TAG = '2026.07.29'
VCPKG_TRIPLET = 'x64-windows-static'


def visual_studio_environment():
    """Environment of vsdevcmd.bat -arch=x64, located with vswhere."""
    vswhere = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'))/'Microsoft Visual Studio'/'Installer'/'vswhere.exe'
    if not vswhere.is_file():
        raise SystemExit('vswhere.exe not found; install Visual Studio 2022 with the C++ x64 tools.')
    installation = subprocess.run([str(vswhere), '-latest', '-products', '*', '-requires',
                                   'Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
                                   '-property', 'installationPath'],
                                  check=True, capture_output=True, text=True).stdout.strip()
    if not installation:
        raise SystemExit('No Visual Studio installation with the C++ x64 tools was found.')
    devcmd = Path(installation)/'Common7'/'Tools'/'vsdevcmd.bat'
    output = subprocess.run(f'"{devcmd}" -arch=x64 -no_logo && set', shell=True, check=True,
                            capture_output=True, text=True).stdout
    environment = dict(os.environ)
    for line in output.splitlines():
        name, separator, value = line.partition('=')
        if separator and name:
            environment[name] = value
    # rawpy's setup.py enables OpenMP only when it finds exactly one vcomp DLL here.
    if not environment.get('VCToolsRedistDir') or environment.get('VSCMD_ARG_TGT_ARCH') != 'x64':
        raise SystemExit('The Visual Studio x64 environment is incomplete.')
    return environment


def install_vcpkg_dependencies(environment):
    vcpkg = WORK/'vcpkg'
    if not (vcpkg/'vcpkg.exe').is_file():
        shutil.rmtree(vcpkg, ignore_errors=True)
        run(['git', 'clone', 'https://github.com/microsoft/vcpkg', '-b', VCPKG_TAG, '--depth', '1', vcpkg])
        run(['cmd', '/c', vcpkg/'bootstrap-vcpkg.bat', '-disableMetrics'], cwd=vcpkg, env=environment)
    run([vcpkg/'vcpkg.exe', 'install', 'zlib', 'libjpeg-turbo[jpeg8]', 'jasper', 'lcms',
         f'--triplet={VCPKG_TRIPLET}', '--recurse'], cwd=vcpkg, env=environment)
    return {**environment,
            'CMAKE_PREFIX_PATH': str(vcpkg/'installed'/VCPKG_TRIPLET),
            'CMAKE_TOOLCHAIN_FILE': str(vcpkg/'scripts'/'buildsystems'/'vcpkg.cmake'),
            'VCPKG_TARGET_TRIPLET': VCPKG_TRIPLET}


def verify(wheel):
    """Import the built wheel in isolation and check OpenMP and the patch label."""
    with tempfile.TemporaryDirectory(prefix='kora-rawpy-') as target:
        run([sys.executable, '-m', 'pip', 'install', '--no-deps', '--target', target, wheel])
        report = subprocess.run([sys.executable, '-c',
                                 'import json, rawpy; print(json.dumps({"version": rawpy.__version__, '
                                 '"flags": rawpy.flags, "file": rawpy.__file__}))'],
                                env={**os.environ, 'PYTHONPATH': target}, check=True,
                                capture_output=True, text=True, cwd=target).stdout
    result = json.loads(report)
    if not result['flags'].get('OPENMP') or not result['version'].endswith(PATCHED_LABEL):
        raise SystemExit(f'Unexpected rawpy build: {result}')
    print(json.dumps(result))


def main():
    if sys.platform != 'win32' or sysconfig.get_platform() != 'win-amd64':
        raise SystemExit('Build this wheel with 64-bit Python on Windows x64.')
    WORK.mkdir(parents=True, exist_ok=True)
    WHEELS.mkdir(parents=True, exist_ok=True)
    environment = install_vcpkg_dependencies(visual_studio_environment())
    source = prepare_rawpy_source(WORK)
    for old in WHEELS.glob('rawpy-*.whl'):
        old.unlink()
    run([sys.executable, '-m', 'pip', 'wheel', source, '--wheel-dir', WHEELS, '--no-deps'],
        env=environment)
    wheel = next(WHEELS.glob('rawpy-*.whl'))
    verify(wheel)
    print(f'Built {wheel}')


if __name__ == '__main__':
    try:
        main()
    except SystemExit as stop:
        if stop.code not in (None, 0) and os.environ.get('GITHUB_ACTIONS'):
            print(f'::error title=rawpy build::{stop.code}', flush=True)
        raise
