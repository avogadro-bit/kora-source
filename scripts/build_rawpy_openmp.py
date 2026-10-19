"""Build a macOS rawpy wheel whose LibRaw uses all CPU cores (OpenMP).

The PyPI macOS wheels of rawpy compile LibRaw without OpenMP, so demosaicing
(notably the 3-pass X-Trans algorithm) runs on one core. This script builds,
from pinned and hash-verified upstream sources:

1. LLVM's OpenMP runtime (libomp) for the release macOS minimum,
2. the codec and colour libraries of rawpy's own macOS CI, same versions and
   options (.github/scripts/build-macos.sh at v0.27.1), and
3. rawpy with its bundled LibRaw compiled with OpenMP, then delocated so every
   library travels inside the wheel.

With OpenMP, LibRaw's X-Trans output varied between runs: demosaic tile rows
read pixels their neighbours were still writing, and half-size copies let
threads race for the same pixel. packaging/libraw-xtrans-deterministic-openmp.patch
orders both and reproduces the single-threaded result exactly.

Homebrew libraries are never linked. The wheel is written to build/wheels/.
It is only built, never published. --install also installs it into the running
interpreter's environment and checks the result.

    .venv-macos-release/bin/python scripts/build_rawpy_openmp.py --install
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
XTRANS_PATCH = ROOT/'packaging'/'libraw-xtrans-deterministic-openmp.patch'
# Local version label of every patched build. Release builds refuse a rawpy
# without it, so an unpatched (non-deterministic OpenMP) wheel cannot ship.
PATCHED_LABEL = 'kora.xtrans1'
WORK = ROOT/'build'/'rawpy-openmp'
WHEELS = ROOT/'build'/'wheels'
MACOS_MINIMUM = '14.0'

RAWPY_VERSION = '0.27.1'
RAWPY_URL = ('https://files.pythonhosted.org/packages/f3/ae/c1c7816ed3f3cbf7ca284a37371243500f4eb39b6a32f7368b585c4ef5c4/'
             f'rawpy-{RAWPY_VERSION}.tar.gz')
RAWPY_SHA256 = '3194d64ff690ac945e1a43237edae8a18f1f493751924de1ae2bcef473c0fb79'
LLVM_VERSION = '22.1.8'
LLVM_URL = (f'https://github.com/llvm/llvm-project/releases/download/llvmorg-{LLVM_VERSION}/'
            f'llvm-project-{LLVM_VERSION}.src.tar.xz')
LLVM_SHA256 = '922f1817a0df7b1489272d18134ee0087a8b068828f87ac63b9861b1a9965888'
# Same sources and checksums as rawpy v0.27.1's macOS wheel build.
LIBJPEG_URL = 'https://github.com/libjpeg-turbo/libjpeg-turbo/releases/download/3.1.3/libjpeg-turbo-3.1.3.tar.gz'
LIBJPEG_SHA256 = '075920b826834ac4ddf97661cc73491047855859affd671d52079c6867c1c6c0'
JASPER_URL = 'https://github.com/jasper-software/jasper/archive/version-4.2.5.tar.gz'
JASPER_SHA256 = '3f4b1df7cab7a3cc67b9f6e28c730372f030b54b0faa8548a9ee04ae83fffd44'
LCMS_URL = 'https://downloads.sourceforge.net/project/lcms/lcms/2.11/lcms2-2.11.tar.gz'
LCMS_SHA256 = 'dc49b9c8e4d7cdff376040571a722902b682a795bf92985a85b48854c270772e'


def require_release_rawpy(require_patched):
    """Refuse a release whose rawpy could make X-Trans renders vary between runs.

    Any OpenMP LibRaw must carry the ordering patch. Where a patched build is
    provided (Apple Silicon, Windows x64) it is required, so a release cannot
    silently fall back to the slower single-threaded decoder either.
    """
    import rawpy
    patched = rawpy.__version__.endswith('+' + PATCHED_LABEL)
    if rawpy.flags.get('OPENMP') and not patched:
        raise SystemExit(f'rawpy {rawpy.__version__} uses OpenMP without the deterministic X-Trans patch. '
                         'Install the wheel built by scripts/build_rawpy_openmp.py or build_rawpy_windows.py.')
    if require_patched and not (patched and rawpy.flags.get('OPENMP')):
        raise SystemExit(f'rawpy {rawpy.__version__} is not the deterministic OpenMP build required here. '
                         'Install the wheel built by scripts/build_rawpy_openmp.py or build_rawpy_windows.py.')
    return {'version': rawpy.__version__, 'openmp': bool(rawpy.flags.get('OPENMP')), 'xtrans_patch': patched}


def run(command, **kwargs):
    print('+', ' '.join(str(part) for part in command), flush=True)
    subprocess.run([str(part) for part in command], check=True, **kwargs)


def download(url, digest, destination):
    if not destination.is_file() or hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
        print(f'Downloading {url}', flush=True)
        partial = destination.with_suffix(destination.suffix + '.part')
        with urllib.request.urlopen(url, timeout=120) as response, partial.open('wb') as stream:
            shutil.copyfileobj(response, stream)
        partial.replace(destination)
    actual = hashlib.sha256(destination.read_bytes()).hexdigest()
    if actual != digest:
        destination.unlink()
        raise SystemExit(f'Checksum mismatch for {destination.name}: {actual}')
    return destination


def macos_sdk():
    """Prefer Xcode's SDK: a newer Command Line Tools SDK can be unreadable by its linker."""
    override = os.environ.get('KORA_MACOS_SDK')
    if override:
        return Path(override)
    developer = Path(subprocess.run(['xcode-select', '-p'], check=True, capture_output=True,
                                    text=True).stdout.strip())
    candidate = developer/'Platforms'/'MacOSX.platform'/'Developer'/'SDKs'/'MacOSX.sdk'
    if candidate.is_dir():
        return candidate
    return Path(subprocess.run(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], check=True,
                               capture_output=True, text=True).stdout.strip())


def safe_extract(archive, destination, members=None):
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as source:
        selected = [m for m in source.getmembers()
                    if members is None or any(m.name == p or m.name.startswith(p + '/') for p in members)]
        source.extractall(destination, members=selected, filter='data')
        return destination/selected[0].name.split('/')[0]


def cmake_install(source, build, prefix, environment, *options):
    shutil.rmtree(build, ignore_errors=True)
    run(['cmake', '-S', source, '-B', build, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
         f'-DCMAKE_OSX_SYSROOT={environment["SDKROOT"]}', '-DCMAKE_OSX_ARCHITECTURES=arm64',
         f'-DCMAKE_OSX_DEPLOYMENT_TARGET={MACOS_MINIMUM}', f'-DCMAKE_INSTALL_PREFIX={prefix}',
         f'-DCMAKE_PREFIX_PATH={prefix}', '-DCMAKE_IGNORE_PREFIX_PATH=/opt/homebrew;/usr/local',
         *options], env=environment)
    run(['ninja', '-C', build, 'install'], env=environment)


def build_dependencies(prefix, environment):
    """libjpeg-turbo, JasPer and Little CMS, configured like rawpy's macOS CI."""
    jpeg = safe_extract(download(LIBJPEG_URL, LIBJPEG_SHA256, WORK/'libjpeg-turbo-3.1.3.tar.gz'), WORK)
    cmake_install(jpeg, WORK/'libjpeg-build', prefix, environment, f'-DCMAKE_INSTALL_NAME_DIR={prefix}/lib',
                  '-DENABLE_SHARED=ON', '-DENABLE_STATIC=OFF', '-DWITH_JPEG8=ON')
    jasper = safe_extract(download(JASPER_URL, JASPER_SHA256, WORK/'jasper-4.2.5.tar.gz'), WORK)
    cmake_install(jasper, WORK/'jasper-build', prefix, environment, f'-DCMAKE_INSTALL_NAME_DIR={prefix}/lib',
                  '-DJAS_ENABLE_OPENGL=OFF', '-DJAS_ENABLE_DOC=OFF', '-DJAS_ENABLE_PROGRAMS=OFF')
    lcms = safe_extract(download(LCMS_URL, LCMS_SHA256, WORK/'lcms2-2.11.tar.gz'), WORK)
    run(['./configure', f'--prefix={prefix}', '--without-jpeg', '--without-tiff'], cwd=lcms, env=environment)
    run(['make', 'install', f'-j{os.cpu_count()}'], cwd=lcms, env=environment)


def build_libomp(sources, prefix, environment):
    """LLVM OpenMP runtime only, built for the release macOS minimum."""
    llvm = WORK/f'llvm-project-{LLVM_VERSION}.src'
    if not (llvm/'openmp').is_dir():
        root = f'llvm-project-{LLVM_VERSION}.src'
        safe_extract(sources, WORK, [f'{root}/{part}' for part in ('openmp', 'cmake', 'llvm/cmake', 'runtimes')])
    # An absolute install name lets delocate find and rewrite it into the wheel.
    cmake_install(llvm/'openmp', WORK/'libomp-build', prefix, environment, f'-DCMAKE_INSTALL_NAME_DIR={prefix}/lib',
                  '-DLIBOMP_ENABLE_SHARED=ON', '-DLIBOMP_OMPT_SUPPORT=OFF', '-DLIBOMP_USE_HWLOC=OFF',
                  '-DOPENMP_ENABLE_LIBOMPTARGET=OFF', '-DLIBOMP_INSTALL_ALIASES=OFF')


def prepare_rawpy_source(work):
    """Extract the verified rawpy sdist, apply the X-Trans patch and mark the version."""
    source = work/f'rawpy-{RAWPY_VERSION}'
    shutil.rmtree(source, ignore_errors=True)
    safe_extract(download(RAWPY_URL, RAWPY_SHA256, work/Path(RAWPY_URL).name), work)
    # Stop git from discovering this checkout when build/ sits inside it, so
    # the patch applies relative to the extracted source like GNU patch.
    run(['git', 'apply', '-p1', '--directory=external/LibRaw', XTRANS_PATCH], cwd=source,
        env={**os.environ, 'GIT_CEILING_DIRECTORIES': str(source.parent)})
    libraw = source/'external'/'LibRaw'/'src'
    if ('tiles_done' not in (libraw/'demosaic'/'xtrans_demosaic.cpp').read_text(encoding='utf-8')
            or 'rowsPerImageRow' not in (libraw/'preprocessing'/'raw2image.cpp').read_text(encoding='utf-8')):
        raise SystemExit('The deterministic OpenMP patch was not applied.')
    version = source/'rawpy'/'_version.py'
    marked = version.read_text(encoding='utf-8').replace(f'"{RAWPY_VERSION}"', f'"{RAWPY_VERSION}+{PATCHED_LABEL}"')
    if PATCHED_LABEL not in marked:
        raise SystemExit('Cannot mark the patched rawpy version.')
    version.write_text(marked, encoding='utf-8')
    return source


def enable_macos_openmp(source, prefix):
    """Turn on LibRaw's OpenMP build for macOS against the libraries built above."""
    setup = source/'setup.py'
    text = setup.read_text(encoding='utf-8')
    include, library = prefix/'include', prefix/'lib'/'libomp.dylib'
    flags = f'-Xpreprocessor -fopenmp -I{include}'
    replacements = [
        ('enable_openmp = "ON" if isLinux else "OFF"', 'enable_openmp = "ON"'),
        ('        "-DCMAKE_INSTALL_NAME_DIR=" + install_name_dir,\n    ]',
         '        "-DCMAKE_INSTALL_NAME_DIR=" + install_name_dir,\n'
         f'        \'-DOpenMP_C_FLAGS="{flags}"\', \'-DOpenMP_CXX_FLAGS="{flags}"\',\n'
         '        "-DOpenMP_C_LIB_NAMES=omp", "-DOpenMP_CXX_LIB_NAMES=omp",\n'
         f'        "-DOpenMP_omp_LIBRARY={library}",\n'
         f'        "-DCMAKE_OSX_DEPLOYMENT_TARGET={MACOS_MINIMUM}", "-DCMAKE_OSX_ARCHITECTURES=arm64",\n'
         f'        "-DCMAKE_PREFIX_PATH={prefix}", \'"-DCMAKE_IGNORE_PREFIX_PATH=/opt/homebrew;/usr/local"\',\n'
         '        \'-DCMAKE_SHARED_LINKER_FLAGS="-Wl,-rpath,@loader_path"\',\n    ]'),
    ]
    for old, new in replacements:
        if text.count(old) != 1:
            raise SystemExit(f'rawpy {RAWPY_VERSION} setup.py changed; cannot apply: {old[:60]!r}')
        text = text.replace(old, new)
    setup.write_text(text, encoding='utf-8')


def install_and_verify(wheel):
    """Install into this interpreter's environment, then import it from a clean process."""
    run(['uv', 'pip', 'install', '--python', sys.executable, '--no-deps', '--reinstall', wheel])
    report = json.loads(subprocess.run(
        [sys.executable, '-c', 'import json, rawpy; print(json.dumps({"version": rawpy.__version__, '
         '"libraw": rawpy.libraw_version, "flags": rawpy.flags}))'],
        check=True, capture_output=True, text=True, cwd=WORK,
        env={k: v for k, v in os.environ.items() if not k.startswith(('DYLD_', 'PYTHONPATH'))}).stdout)
    if (not report['flags'].get('OPENMP') or not report['version'].endswith('+' + PATCHED_LABEL)
            or tuple(report['libraw']) != (0, 22, 1)):
        raise SystemExit(f'Unexpected installed rawpy: {report}')
    print(json.dumps(report))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--install', action='store_true',
                        help="install the wheel into this interpreter's environment and verify it")
    args = parser.parse_args()
    if sys.platform != 'darwin' or platform.machine() != 'arm64':
        raise SystemExit('This build targets Apple Silicon macOS.')
    for tool in ('cmake', 'ninja', 'make', 'uv', 'uvx'):
        if shutil.which(tool) is None:
            raise SystemExit(f'{tool} is required on PATH.')
    WORK.mkdir(parents=True, exist_ok=True)
    WHEELS.mkdir(parents=True, exist_ok=True)
    prefix = WORK/'prefix'
    shutil.rmtree(prefix, ignore_errors=True)
    # Only the libraries built here may be found: no Homebrew pkg-config,
    # headers or dylibs, whose minimum macOS follows the build machine.
    environment = {**os.environ, 'SDKROOT': str(macos_sdk()), 'MACOSX_DEPLOYMENT_TARGET': MACOS_MINIMUM,
                   'ARCHFLAGS': '-arch arm64', 'CC': 'clang', 'CXX': 'clang++',
                   'CFLAGS': '-arch arm64', 'CXXFLAGS': '-arch arm64', 'LDFLAGS': '-arch arm64',
                   'PKG_CONFIG_LIBDIR': str(prefix/'lib'/'pkgconfig'), 'PKG_CONFIG_PATH': '',
                   'CMAKE_PREFIX_PATH': str(prefix), 'LIBRARY_PATH': str(prefix/'lib')}
    build_libomp(download(LLVM_URL, LLVM_SHA256, WORK/Path(LLVM_URL).name), prefix, environment)
    build_dependencies(prefix, environment)
    source = prepare_rawpy_source(WORK)
    enable_macos_openmp(source, prefix)
    # LibRaw's public headers include <omp.h> once OpenMP is enabled.
    environment['CPPFLAGS'] = f'-I{prefix/"include"}'
    unrepaired = WORK/'wheel'
    shutil.rmtree(unrepaired, ignore_errors=True)
    run(['uv', 'build', '--wheel', '--python', sys.executable, '--out-dir', unrepaired, source], env=environment)
    for old in WHEELS.glob('rawpy-*.whl'):
        old.unlink()
    # Copy libomp, LibRaw's codecs and Little CMS into the wheel, like rawpy's CI.
    run(['uvx', '--from', 'delocate', 'delocate-wheel', '--require-archs=arm64', '-w', WHEELS,
         next(unrepaired.glob('rawpy-*.whl'))], env={**environment, 'DYLD_LIBRARY_PATH': str(prefix/'lib')})
    wheel = next(WHEELS.glob('rawpy-*.whl'))
    print(f'Built {wheel}')
    if args.install:
        install_and_verify(wheel)


if __name__ == '__main__':
    main()
