"""Check tracked and unignored files before sharing. Does not stage or publish."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
BLOCKED={'.cube','.raf','.dng','.cr2','.cr3','.nef','.arw','.rw2','.iiq',
         '.jpg','.jpeg','.tif','.tiff','.npz','.npy','.bin','.dat','.zip','.pem','.key'}
SECRET=re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
HOME_PATH=re.compile(r'/(?:Users|home)/[A-Za-z0-9_.-]+/')


def main():
    result=subprocess.run(['git','ls-files','--cached','--others','--exclude-standard','-z'],
                          cwd=ROOT,check=True,capture_output=True)
    files=sorted(set(p for p in result.stdout.decode().split('\0') if p))
    failures=[];total=0
    for name in files:
        p=ROOT/name
        if not p.exists():continue
        if p.is_symlink():failures.append((name,'symbolic link'));continue
        total+=p.stat().st_size
        if name.startswith(('research/','outputs/')) and p.name!='.gitkeep':
            failures.append((name,'private research/output'))
        if name=='kora/film_data/kodachrome64_v1.npz':
            meta=json.loads((p.with_suffix('.json')).read_text())
            if p.stat().st_size>8*1024*1024 or hashlib.sha256(p.read_bytes()).hexdigest()!=meta['sha256']:
                failures.append((name,'invalid generated scientific table'))
            continue
        if p.suffix.lower() in BLOCKED or p.stat().st_size>2*1024*1024:
            failures.append((name,'binary asset or oversized file'))
        try:text=p.read_text(encoding='utf-8')
        except UnicodeError:
            failures.append((name,'unexpected binary'));continue
        if SECRET.search(text):failures.append((name,'possible credential (value redacted)'))
        if HOME_PATH.search(text):failures.append((name,'absolute personal home path'))
    for name,reason in failures:print(f'FAIL {name}: {reason}')
    print(f'{len(files)} files, {total/1024/1024:.2f} MiB; {len(failures)} finding(s).')
    return bool(failures)


if __name__=='__main__':sys.exit(main())
