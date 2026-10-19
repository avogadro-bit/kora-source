"""Build a self-contained rawpy 0.27.1 wheel for Mac Intel (no upstream wheel).

Run with the isolated Intel release Python. Dependencies stay under build/ and
are repaired into the wheel by delocate; no Homebrew/system installation changes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    'libjpeg-turbo-3.1.3': (
        'https://codeload.github.com/libjpeg-turbo/libjpeg-turbo/tar.gz/refs/tags/3.1.3',
        '3a13a5ba767dc8264bc40b185e41368a80d5d5f945944d1dbaa4b2fb0099f4e5'),
    'lcms2-2.11': (
        'https://codeload.github.com/mm2/Little-CMS/tar.gz/refs/tags/2.11',
        '478c9c3938d7a91b1171de4616f8b04308a8676d73eadc19505b7ace41327f28'),
    'jasper-4.2.5': (
        'https://codeload.github.com/jasper-software/jasper/tar.gz/refs/tags/version-4.2.5',
        '3f4b1df7cab7a3cc67b9f6e28c730372f030b54b0faa8548a9ee04ae83fffd44'),
    'rawpy-0.27.1': (
        'https://files.pythonhosted.org/packages/f3/ae/c1c7816ed3f3cbf7ca284a37371243500f4eb39b6a32f7368b585c4ef5c4/rawpy-0.27.1.tar.gz',
        '3194d64ff690ac945e1a43237edae8a18f1f493751924de1ae2bcef473c0fb79'),
}
EXPECTED_FLAGS = {'DNGLOSSYCODEC': True, 'DNGDEFLATECODEC': True, 'OPENMP': False,
                  'LCMS': True, 'REDCINECODEC': True, 'RAWSPEED': False,
                  'DEMOSAIC_PACK_GPL2': False, 'DEMOSAIC_PACK_GPL3': False,
                  'X3FTOOLS': True, '6BY9RPI': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, help='Matching macOS SDK; defaults to xcrun selection')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/intel-runtime/native')
    parser.add_argument('--source-cache', type=Path, default=ROOT / 'build/dependency-sources')
    args = parser.parse_args()
    if sys.platform != 'darwin' or platform.machine() != 'x86_64':
        raise SystemExit('Use a native Intel or Rosetta x86_64 Python on macOS.')
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    prefix = work / 'prefix'
    sdk = args.sdk or Path(subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True).strip())
    if not sdk.is_dir():
        raise SystemExit(f'No macOS SDK: {sdk}')
    toolchain = work / 'intel.cmake'
    toolchain.write_text(
        'set(CMAKE_OSX_ARCHITECTURES "x86_64" CACHE STRING "")\n'
        'set(CMAKE_OSX_DEPLOYMENT_TARGET "14.0" CACHE STRING "")\n'
        f'set(CMAKE_OSX_SYSROOT "{sdk}" CACHE PATH "")\n'
        f'set(CMAKE_PREFIX_PATH "{prefix}" CACHE STRING "")\n'
        'set(CMAKE_IGNORE_PREFIX_PATH "/opt/homebrew;/usr/local" CACHE STRING "")\n', encoding='utf-8')
    # Framework Python can report universal2 even when ARCHFLAGS builds Intel only.
    # Keep the wheel tag consistent with the native library target.
    environment = {**os.environ, 'SDKROOT': str(sdk), 'MACOSX_DEPLOYMENT_TARGET': '14.0',
                   '_PYTHON_HOST_PLATFORM': 'macosx-14.0-x86_64',
                   'ARCHFLAGS': '-arch x86_64', 'CFLAGS': '-arch x86_64 -mmacosx-version-min=14.0',
                   'CXXFLAGS': '-arch x86_64 -mmacosx-version-min=14.0',
                   'CMAKE_TOOLCHAIN_FILE': str(toolchain), 'CMAKE_PREFIX_PATH': str(prefix),
                   'CMAKE_BUILD_PARALLEL_LEVEL': '4',
                   'PKG_CONFIG_PATH': str(prefix / 'lib/pkgconfig'),
                   'PKG_CONFIG_LIBDIR': str(prefix / 'lib/pkgconfig'),
                   'PATH': str(Path(sys.executable).parent) + os.pathsep + os.environ['PATH']}

    def run(*command, cwd=work, env=None):
        print('+', ' '.join(map(str, command)), flush=True)
        subprocess.run(list(map(str, command)), cwd=cwd,
                       env=environment if env is None else env, check=True)

    sources = {}
    for name, (url, digest) in SOURCES.items():
        archive = work / (name + '.tar.gz')
        cached = args.source_cache / archive.name
        if not archive.is_file():
            if cached.is_file() and hashlib.sha256(cached.read_bytes()).hexdigest() == digest:
                shutil.copyfile(cached, archive)
            else:
                with urlopen(url, timeout=120) as source, archive.open('wb') as dest:
                    shutil.copyfileobj(source, dest)
        with archive.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
                raise RuntimeError(f'Source checksum mismatch: {name}')
        destination = work / 'source' / name
        if not destination.is_dir():
            with tarfile.open(archive) as source:
                source.extractall(destination, filter='data')
        sources[name] = next(path for path in destination.iterdir() if path.is_dir())

    def cmake(name, *options):
        build = work / 'cmake' / name
        run('cmake', '-S', sources[name], '-B', build, '-DCMAKE_BUILD_TYPE=Release',
            '-DCMAKE_INSTALL_PREFIX=' + str(prefix), *options)
        run('cmake', '--build', build, '--parallel', '4')
        run('cmake', '--install', build)

    # A non-SIMD libjpeg fallback avoids requiring a second assembler toolchain;
    # it affects lossy RAW decoding, not Pillow's SIMD-enabled JPEG exports.
    cmake('libjpeg-turbo-3.1.3', '-DENABLE_SHARED=ON', '-DENABLE_STATIC=OFF',
          '-DWITH_JPEG8=ON', '-DWITH_SIMD=' + ('ON' if shutil.which('nasm') else 'OFF'))
    lcms = sources['lcms2-2.11']
    run(lcms / 'configure', '--prefix=' + str(prefix), '--host=x86_64-apple-darwin',
        '--disable-static', '--without-jpeg', '--without-tiff', cwd=lcms)
    run('make', '-j4', cwd=lcms)
    run('make', 'install', cwd=lcms)
    cmake('jasper-4.2.5', '-DJAS_ENABLE_SHARED=ON', '-DJAS_ENABLE_PROGRAMS=OFF',
          '-DJAS_ENABLE_DOC=OFF', '-DJAS_ENABLE_OPENGL=OFF')
    wheels = work / 'wheels'
    repaired = work / 'repaired'
    run(sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--no-build-isolation',
        '--wheel-dir', wheels, sources['rawpy-0.27.1'])
    wheel = next(wheels.glob('rawpy-0.27.1-*.whl'))
    if not wheel.name.endswith('-macosx_14_0_x86_64.whl'):
        raise RuntimeError(f'Expected a macOS 14 x86_64 RAW wheel, got {wheel.name}')
    # delocate needs the just-built @rpath dependencies only while repairing.
    # The final import test must not resolve libraries from this build directory.
    run(Path(sys.executable).parent / 'delocate-wheel', '--require-archs=x86_64',
        '-w', repaired, wheel, env={**environment, 'DYLD_LIBRARY_PATH': str(prefix / 'lib')})
    final = next(repaired.glob('rawpy-0.27.1-*.whl'))
    if not final.name.endswith('-macosx_14_0_x86_64.whl'):
        raise RuntimeError(f'Expected a repaired macOS 14 x86_64 RAW wheel, got {final.name}')
    run(sys.executable, '-m', 'pip', 'install', '--no-deps', '--force-reinstall', final)
    run(sys.executable, '-c',
        'import rawpy\n'
        f'if rawpy.flags != {EXPECTED_FLAGS!r}:\n'
        '    raise RuntimeError(f"Unexpected RAW codec flags: {rawpy.flags}")\n'
        'if rawpy.libraw_version != (0, 22, 1):\n'
        '    raise RuntimeError(f"Unexpected LibRaw version: {rawpy.libraw_version}")\n'
        'print(rawpy.__version__, rawpy.libraw_version, rawpy.flags)\n',
        env={key: value for key, value in environment.items() if not key.startswith('DYLD_')})
    (work / 'build-manifest.json').write_text(json.dumps({
        'architecture': 'x86_64', 'deployment_target': '14.0',
        'python': platform.python_version(), 'sdk': str(sdk),
        'sources': {name: {'url': url, 'sha256': digest} for name, (url, digest) in SOURCES.items()},
        'rawpy_flags': EXPECTED_FLAGS,
        'jpeg_simd': bool(shutil.which('nasm')),
        'wheel': final.name, 'sha256': hashlib.sha256(final.read_bytes()).hexdigest(),
    }, indent=2) + '\n', encoding='utf-8')
    print(f'Intel RAW wheel: {final}')


if __name__ == '__main__':
    main()
