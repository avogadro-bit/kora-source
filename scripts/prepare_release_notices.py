"""Collect installed license texts and matching native dependency sources.

Run with the isolated release Python before building the public application.
Downloads are upstream source archives only; no application or photo data.
"""
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import distribution
from pathlib import Path, PurePosixPath
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'build' / 'release-notices'
SOURCES = ROOT / 'build' / 'dependency-sources'
PACKAGES = ('rawpy', 'lensfunpy', 'numpy', 'scipy', 'pillow', 'pydantic',
            'pydantic_core', 'tifffile', 'typing_extensions', 'typing-inspection',
            'annotated-types', 'packaging', 'pyobjc-core', 'pyobjc-framework-Cocoa',
            'pywebview', 'bottle', 'proxy_tools', 'pyobjc-framework-Quartz',
            'pyobjc-framework-WebKit', 'pyobjc-framework-security',
            'pyobjc-framework-UniformTypeIdentifiers')
ARCHIVES = {
    'rawpy-0.27.1': 'https://codeload.github.com/letmaik/rawpy/tar.gz/refs/tags/v0.27.1',
    'LibRaw-b860248': 'https://codeload.github.com/LibRaw/LibRaw/tar.gz/b860248a89d9082b8e0a1e202e516f46af9adb29',
    'LibRaw-cmake-6e26c9e': 'https://codeload.github.com/LibRaw/LibRaw-cmake/tar.gz/6e26c9e73677dc04f9eb236a97c6a4dc225ba7e8',
    'lensfunpy-1.18.0': 'https://codeload.github.com/letmaik/lensfunpy/tar.gz/refs/tags/v1.18.0',
    'lensfun-101c745': 'https://codeload.github.com/lensfun/lensfun/tar.gz/101c745e847a5de4a1e569a94368ce2027198598',
    'glib-2.79.1': 'https://download.gnome.org/sources/glib/2.79/glib-2.79.1.tar.xz',
    'gettext-0.22.4': 'https://ftp.gnu.org/gnu/gettext/gettext-0.22.4.tar.xz',
    'pcre2-10.47': 'https://codeload.github.com/PCRE2Project/pcre2/tar.gz/refs/tags/pcre2-10.47',
    'libffi-3.5.2': 'https://codeload.github.com/libffi/libffi/tar.gz/refs/tags/v3.5.2',
    'libjpeg-turbo-3.1.3': 'https://codeload.github.com/libjpeg-turbo/libjpeg-turbo/tar.gz/refs/tags/3.1.3',
    'jasper-4.2.5': 'https://codeload.github.com/jasper-software/jasper/tar.gz/refs/tags/version-4.2.5',
    'lcms2-2.11': 'https://codeload.github.com/mm2/Little-CMS/tar.gz/refs/tags/2.11',
}
LICENSE_TEXTS = {
    'Lensfun-LGPL-3.0.txt': 'https://www.gnu.org/licenses/lgpl-3.0.txt',
    'Lensfun-GPL-3.0.txt': 'https://www.gnu.org/licenses/gpl-3.0.txt',
    'Lensfun-database-CC-BY-SA-3.0.txt': 'https://raw.githubusercontent.com/lensfun/lensfun/master/data/COPYING.CC_BY-SA_3.0',
}


def license_file(path):
    name = PurePosixPath(str(path)).name.lower()
    return name.startswith(('license', 'copying', 'copyright', 'notice')) or 'LICENSES' in PurePosixPath(str(path)).parts


def download(item):
    name, url = item
    target = SOURCES / (name + ('.tar.xz' if url.endswith('.xz') else '.tar.gz'))
    if not target.exists():
        subprocess.run(['curl', '-fL', '--retry', '2', '--silent', '--show-error', url, '-o', str(target)], check=True)
    with tarfile.open(target) as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if member.isfile() and license_file(path) and '..' not in path.parts and not path.is_absolute():
                output = DEST / 'native' / name / Path(*path.parts[1:])
                output.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as stream, output.open('wb') as destination:
                    shutil.copyfileobj(stream, destination)
    return {'name': name, 'url': url, 'archive': target.name,
            'sha256': hashlib.file_digest(target.open('rb'), 'sha256').hexdigest()}


def runtime_notices():
    runtime_dir = DEST / 'runtime'
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    prefix = Path(sys.base_prefix)
    build_file = prefix / 'BUILD'
    if sys.platform == 'darwin' and build_file.is_file():
        # uv's install-only runtime omits the third-party license directory.
        # Recover it from the matching full python-build-standalone archive,
        # never from unrelated Homebrew libraries installed on the build Mac.
        build = build_file.read_text().strip()
        if not build.isdigit():
            raise RuntimeError('Invalid Python standalone build identifier')
        python_version = platform.python_version()
        architecture = {'arm64': 'aarch64', 'x86_64': 'x86_64'}[platform.machine()]
        triple = f'{architecture}-apple-darwin'
        name = f'cpython-{python_version}-{build}-full.tar.zst'
        url = (f'https://github.com/astral-sh/python-build-standalone/releases/download/{build}/'
               f'cpython-{python_version}%2B{build}-{triple}-pgo%2Blto-full.tar.zst')
        archive_path = ROOT / 'build' / 'runtime-archives' / name
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        if not archive_path.is_file():
            subprocess.run(['curl', '-fL', '--retry', '2', '--silent', '--show-error',
                            url, '-o', str(archive_path)], check=True)
        copied = []
        with tarfile.open(archive_path) as archive:
            metadata = json.load(archive.extractfile('python/PYTHON.json'))
            if metadata['python_version'] != python_version or metadata['target_triple'] != triple:
                raise RuntimeError('Python runtime notice archive does not match interpreter')
            for member in archive:
                path = PurePosixPath(member.name)
                if member.isfile() and path.parts[:2] == ('python', 'licenses') and '..' not in path.parts:
                    target = runtime_dir / 'python-build-standalone' / Path(*path.parts[2:])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as stream, target.open('wb') as output:
                        shutil.copyfileobj(stream, output)
                    copied.append(str(target.relative_to(DEST)))
        if not copied:
            raise RuntimeError('Standalone Python archive has no dependency licenses')
        return {'distribution': 'python-build-standalone', 'build': build, 'url': url,
                'sha256': hashlib.file_digest(archive_path.open('rb'), 'sha256').hexdigest(),
                'licenses': copied, 'minimum_macos': metadata['apple_sdk_deployment_target']}
    runtime_licenses = {
        'Python': prefix.parents[3] / 'LICENSE',
        'OpenSSL': Path('/opt/homebrew/opt/openssl@3/LICENSE.txt'),
        'zstd': Path('/opt/homebrew/opt/zstd/LICENSE'),
        'mpdecimal': Path('/opt/homebrew/opt/mpdecimal/COPYRIGHT.txt'),
    } if sys.platform == 'darwin' else {'Python': prefix / 'LICENSE.txt'}
    for name, source in runtime_licenses.items():
        target = runtime_dir / name / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return {'distribution': 'Homebrew' if sys.platform == 'darwin' else 'python.org'}


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    SOURCES.mkdir(parents=True, exist_ok=True)
    packages = []
    package_names = PACKAGES
    if sys.platform == 'win32':
        package_names = tuple(name for name in PACKAGES if not name.startswith('pyobjc-')) + ('pythonnet', 'clr_loader', 'cffi', 'pycparser')
    for name in package_names:
        dist = distribution(name)
        copied = []
        package_dir = DEST / 'python-packages' / name
        if package_dir.exists():
            shutil.rmtree(package_dir)
        for entry in dist.files:
            if license_file(entry) and not any(part == 'PyObjCTest' for part in entry.parts):
                target = DEST / 'python-packages' / name / str(entry)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(dist.locate_file(entry), target)
                copied.append(str(target.relative_to(DEST)))
        # The core wheel declares MIT but omits the actual license file.
        if not copied and name.startswith('pyobjc-'):
            target = package_dir / 'License.txt'
            target.parent.mkdir(parents=True, exist_ok=True)
            source_name = 'pyobjc-framework-Security' if name.endswith('security') else name
            url = f'https://raw.githubusercontent.com/ronaldoussoren/pyobjc/v{dist.version}/{source_name}/License.txt'
            subprocess.run(['curl', '-fL', '--retry', '2', '--silent', '--show-error', url, '-o', str(target)], check=True)
            copied.append(str(target.relative_to(DEST)))
        if not copied and name == 'proxy_tools':
            target = package_dir / 'LICENSE'
            target.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(['curl', '-fL', '--retry', '2', '--silent', '--show-error',
                            'https://raw.githubusercontent.com/jtushman/proxy_tools/master/LICENSE.txt',
                            '-o', str(target)], check=True)
            copied.append(str(target.relative_to(DEST)))
        if not copied:
            raise RuntimeError(f'No installed license found: {name}')
        packages.append({'name': name, 'version': dist.version, 'licenses': copied,
                         'upstream': dist.metadata.get_all('Project-URL') or [dist.metadata.get('Home-page', '')]})
    runtime = runtime_notices()
    with ThreadPoolExecutor(max_workers=4) as pool:
        sources = list(pool.map(download, ARCHIVES.items()))
    for name, url in LICENSE_TEXTS.items():
        target = DEST / name
        cached = SOURCES / name
        if cached.is_file() and cached.stat().st_size:
            shutil.copyfile(cached, target)
        else:
            subprocess.run(['curl', '-fL', '--retry', '2', '--connect-timeout', '15',
                            '--max-time', '90', '--silent', '--show-error', url, '-o', str(target)], check=True)
        shutil.copyfile(target, SOURCES/name)
    lens_database = ROOT / 'kora' / 'lensfun_db'
    for destination in (DEST, SOURCES):
        shutil.copytree(lens_database, destination/'lensfun-database', dirs_exist_ok=True)
    manifest = {'python': sys.version.split()[0], 'runtime': runtime, 'packages': packages, 'native_sources': sources,
                'lens_database': json.loads((lens_database/'origin.json').read_text())}
    (DEST/'inventory.json').write_text(json.dumps(manifest, indent=2)+'\n')
    (SOURCES/'inventory.json').write_text(json.dumps(manifest, indent=2)+'\n')
    shutil.copyfile(ROOT/'docs'/'DEPENDENCY_NOTICES.md', DEST/'README.md')
    shutil.copyfile(ROOT/'docs'/'DEPENDENCY_NOTICES.md', SOURCES/'README.md')
    print(f'Collected {len(packages)} package notices and {len(sources)} source archives.')


if __name__ == '__main__':
    main()
