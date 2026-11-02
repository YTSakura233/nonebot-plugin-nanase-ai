"""Validate and export a portable knowledge ZIP plus a download checksum."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile
from packlib import ROOT


def main():
    subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scripts/build_pack.py')],check=True)
    subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scripts/validate_pack.py')],check=True)
    dist=ROOT/'dist'
    dist.mkdir(exist_ok=True)
    manifest=json.loads((ROOT/'manifest.json').read_bytes())
    path=dist/f'maimai-knowledge-{manifest["pack_version"]}-{manifest["checked_on"]}.zip'
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(ROOT.rglob('*')):
            relative=file.relative_to(ROOT)
            roots={'README.md','INDEX.md','SOURCES.md','LICENSE','manifest.json','.env.knowledge.example','.gitignore'}
            if relative.parts[0] not in {'corpus','data','examples','scripts','docs'} and relative.as_posix() not in roots:
                continue
            if not file.is_file() or any(p in {'dist','__pycache__','.pytest_cache','.git'} or p.startswith('.staging-') for p in relative.parts):
                continue
            if file.name.startswith('.env') and file.name!='.env.knowledge.example':
                continue
            if file.is_symlink() or not file.resolve().is_relative_to(ROOT.resolve()):
                raise ValueError('package contains a symlink or external path')
            archive.write(file,Path('maimai-knowledge')/relative)
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        assert 'maimai-knowledge/README.md' in archive.namelist()
        assert 'maimai-knowledge/.env.knowledge.example' in archive.namelist()
    record={'file':path.name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    (dist/'checksums.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(record,indent=2))


if __name__=='__main__':
    main()
