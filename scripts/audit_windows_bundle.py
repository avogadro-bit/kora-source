"""Verify Windows app architecture and assets before producing a portable ZIP.

This checks PE headers and packaged files, not Windows API availability. Only a
launch/render test on a target Windows installation can establish that.
"""
import argparse
import json
from pathlib import Path
import struct

if __package__:
    from .audit_package_assets import audit_assets
else:
    from audit_package_assets import audit_assets

MACHINES = {0x14c: 'x86', 0x8664: 'x64', 0xaa64: 'arm64'}


def pe_machine(path):
    """Read PE architecture without loading the file or needing Windows tools."""
    with Path(path).open('rb') as stream:
        dos = stream.read(64)
        if len(dos) != 64 or dos[:2] != b'MZ':
            raise ValueError(f'Not a PE executable: {path}')
        offset = struct.unpack_from('<I', dos, 60)[0]
        if offset < 64 or offset > Path(path).stat().st_size - 6:
            raise ValueError(f'Invalid PE offset: {path}')
        stream.seek(offset)
        header = stream.read(6)
        if header[:4] != b'PE\0\0':
            raise ValueError(f'Invalid PE signature: {path}')
        machine = struct.unpack_from('<H', header, 4)[0]
        return MACHINES.get(machine, f'unknown-{machine:04x}')


def audit_bundle(app):
    app = Path(app).resolve()
    resources = app / '_internal'
    report = audit_assets(resources)
    problems = report['problems']
    required = [app / 'Kora.exe']
    required += list(resources.glob('python3*.dll'))
    extensions = list(resources.rglob('*.pyd'))
    required += extensions
    if not list(resources.glob('python3*.dll')):
        problems.append('Missing bundled Python runtime')
    for module in ('rawpy', 'numpy', 'scipy', 'lensfunpy'):
        if not any(module in str(path.relative_to(resources)) for path in extensions):
            problems.append(f'Missing native extension: {module}')
    webview = resources / 'webview/lib'
    required.append(webview / 'runtimes/win-x64/native/WebView2Loader.dll')
    # These .NET assemblies are portable IL; an x86 PE header does not mean they
    # require 32-bit Python. Only the native WebView2 loader above must be x64.
    for name in ('Microsoft.Web.WebView2.Core.dll', 'Microsoft.Web.WebView2.WinForms.dll'):
        if not (webview / name).is_file():
            problems.append(f'Missing WebView2 assembly: {name}')
    if not list(resources.rglob('Python.Runtime.dll')):
        problems.append('Missing Python.NET runtime assembly')
    binaries = []
    for path in required:
        try:
            architecture = pe_machine(path)
            binaries.append({'path': str(path.relative_to(app)), 'architecture': architecture})
            if architecture != 'x64':
                problems.append(f'{path.relative_to(app)} is {architecture}; expected x64')
        except (OSError, ValueError) as exc:
            problems.append(str(exc))
    return {'compatible': not problems, 'architecture': 'x64',
            'binary_count': len(binaries), 'binaries': binaries, 'problems': problems,
            'scope': 'PE architecture and required files; OS launch compatibility not inferred'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = audit_bundle(args.app)
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    for problem in report['problems']:
        print(problem)
    print(f"Audited {report['binary_count']} native Windows x64 components")
    return 0 if report['compatible'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
