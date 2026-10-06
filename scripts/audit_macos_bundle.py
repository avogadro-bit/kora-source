"""Reject native components newer than the macOS version advertised by Kora."""
import argparse
import json
from pathlib import Path
import plistlib
import re
import subprocess


MACHO_MAGIC = {bytes.fromhex(value) for value in (
    'feedface', 'cefaedfe', 'feedfacf', 'cffaedfe',
    'cafebabe', 'bebafeca', 'cafebabf', 'bfbafeca',
)}


def version(value):
    parts = tuple(int(part) for part in value.split('.'))
    return parts + (0,) * (3 - len(parts))


def deployment_targets(load_commands):
    """Read both current and legacy load commands, never the SDK/linker version."""
    targets = []
    for block in re.split(r'(?m)^Load command \d+\s*$', load_commands):
        if re.search(r'\bcmd LC_BUILD_VERSION\b', block):
            match = re.search(r'^\s*minos (\d+(?:\.\d+){0,2})\s*$', block, re.M)
        elif re.search(r'\bcmd LC_VERSION_MIN_MACOSX\b', block):
            match = re.search(r'^\s*version (\d+(?:\.\d+){0,2})\s*$', block, re.M)
        else:
            continue
        if match:
            targets.append(match.group(1))
    if not targets:
        raise ValueError('Mach-O has no macOS deployment target')
    return targets


def inspect_binary(path, minimum, architecture):
    commands = subprocess.check_output(['otool', '-arch', 'all', '-l', str(path)], text=True)
    targets = deployment_targets(commands)
    archs = subprocess.check_output(['lipo', '-archs', str(path)], text=True).split()
    problems = []
    if architecture not in archs:
        problems.append(f'missing {architecture} architecture')
    if any(version(target) > version(minimum) for target in targets):
        problems.append(f'requires macOS {max(targets, key=version)}; advertised {minimum}')
    # System frameworks are supplied by macOS; build-machine dependencies are not.
    for name in re.findall(r'^\s*(?:name|path) (/.*?) \(offset \d+\)', commands, re.M):
        if not name.startswith(('/usr/lib/', '/System/Library/')):
            problems.append(f'external load path: {name}')
    return {'targets': targets, 'architectures': archs, 'problems': problems}


def audit_bundle(app, architecture):
    app = Path(app).resolve()
    with (app / 'Contents' / 'Info.plist').open('rb') as stream:
        minimum = plistlib.load(stream)['LSMinimumSystemVersion']
    binaries, seen = [], set()
    for path in sorted(app.rglob('*')):
        if not path.is_file():
            continue
        real = path.resolve()
        if not real.is_relative_to(app):
            raise ValueError(f'Bundle file points outside application: {path.relative_to(app)}')
        if real in seen:
            continue
        seen.add(real)
        with real.open('rb') as stream:
            if stream.read(4) not in MACHO_MAGIC:
                continue
        result = inspect_binary(real, minimum, architecture)
        binaries.append({'path': str(path.relative_to(app)), **result})
    if not binaries:
        raise ValueError('No Mach-O binaries found')
    failures = [entry for entry in binaries if entry['problems']]
    return {'minimum_macos': minimum, 'architecture': architecture,
            'binary_count': len(binaries), 'compatible': not failures, 'binaries': binaries}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', type=Path)
    parser.add_argument('--architecture', default='arm64')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = audit_bundle(args.app, args.architecture)
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    for entry in report['binaries']:
        for problem in entry['problems']:
            print(f"{entry['path']}: {problem}")
    print(f"Audited {report['binary_count']} binaries for macOS {report['minimum_macos']} ({args.architecture})")
    return 0 if report['compatible'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
