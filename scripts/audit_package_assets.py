"""Check essential runtime assets in a frozen app, independently of source files."""
import argparse
import hashlib
import json
from pathlib import Path


def audit_assets(resources):
    resources = Path(resources)
    required = ('kora/static/index.html', 'kora/static/app.js', 'kora/static/style.css',
                'kora/static/kora.css', 'kora/static/diagnostics.js', 'kora/static/viewer.js',
                'kora/lensfun_db/origin.json', 'kora/film_data/NOTICE.txt',
                'kora/film_data/kodachrome64_v1.json',
                'kora/film_data/kodachrome64_v1.npz', 'Third-Party-Notices/inventory.json')
    problems = [f'Missing or empty packaged asset: {name}' for name in required
                if not (resources / name).is_file() or not (resources / name).stat().st_size]
    if not list((resources / 'kora/lensfun_db').glob('*.xml')):
        problems.append('No packaged lens correction database')
    manifest = resources / 'kora/film_data/kodachrome64_v1.json'
    table = resources / 'kora/film_data/kodachrome64_v1.npz'
    if manifest.is_file() and table.is_file():
        expected = json.loads(manifest.read_text(encoding='utf-8'))['sha256']
        with table.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if expected != actual:
            problems.append('Packaged Kodachrome model checksum does not match its manifest')
    return {'compatible': not problems, 'problems': problems}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('resources', type=Path)
    args = parser.parse_args()
    report = audit_assets(args.resources)
    print(json.dumps(report, indent=2))
    return 0 if report['compatible'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
