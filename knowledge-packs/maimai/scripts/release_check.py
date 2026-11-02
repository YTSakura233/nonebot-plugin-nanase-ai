"""Extract and test the packaged ZIP in a fresh local directory."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
from packlib import ROOT


def main():
    manifest=json.loads((ROOT/'manifest.json').read_bytes())
    archive_path=ROOT/'dist'/f'maimai-knowledge-{manifest["pack_version"]}-{manifest["checked_on"]}.zip'
    with tempfile.TemporaryDirectory(prefix='.staging-release-',dir=ROOT) as temporary:
        stage=Path(temporary).resolve()
        if not stage.is_relative_to(ROOT.resolve()):
            raise ValueError('release test path escapes pack root')
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                if not (stage/member.filename).resolve().is_relative_to(stage):
                    raise ValueError('unsafe ZIP entry')
            archive.extractall(stage)
        bundle=stage/'maimai-knowledge'
        checks=subprocess.run([sys.executable,'-X','utf8','scripts/validate_pack.py'],cwd=bundle,
                              capture_output=True,text=True,encoding='utf-8',timeout=60)
        if checks.returncode:
            raise RuntimeError(checks.stdout+checks.stderr)
        lookup=subprocess.run([sys.executable,'-X','utf8','scripts/lookup.py','真爱歌'],cwd=bundle,
                              capture_output=True,text=True,encoding='utf-8',check=True,timeout=20)
        result=json.loads(lookup.stdout)
        assert result[0]['id']==8 and result[0]['title']=='True Love Song'
        assert (bundle/'.env.knowledge.example').is_file()
    print('RELEASE_OK: fresh ZIP extraction, 15 offline checks, alias lookup, configuration example')


if __name__=='__main__':
    main()
