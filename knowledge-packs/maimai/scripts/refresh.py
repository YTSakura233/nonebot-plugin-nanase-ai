"""Explicit public-metadata refresh. Never called by the bot or a Skill."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
import urllib.request

from packlib import ROOT, validate_lxns, validate_cn, validate_aliases
from build_pack import build

SOURCES = {
    'lxns_songs': 'https://maimai.lxns.net/api/v0/maimai/song/list?version={version}&notes=true',
    'lxns_aliases': 'https://maimai.lxns.net/api/v0/maimai/alias/list',
    'cn_maidata': 'https://raw.githubusercontent.com/CrazyKidCN/maimaiDX-CN-songs-database/main/maidata.json',
}


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent':'Nanase-Maimai-Knowledge/1.0'})
    with urllib.request.urlopen(request, timeout=15) as response:
        content = response.read(16*1024*1024+1)
    if len(content)>16*1024*1024:
        raise ValueError('public metadata exceeds 16 MiB')
    json.loads(content)
    return content


def main():
    parser = argparse.ArgumentParser(description='刷新公开曲库；先验证，再发布。请先保留上一个ZIP备份。')
    parser.add_argument('--game-version',type=int,default=25500)
    parser.add_argument('--dry-run',action='store_true',help='下载和验证，不替换本地快照')
    args = parser.parse_args()
    urls = {k:v.format(version=args.game_version) for k,v in SOURCES.items()}
    contents = {key:fetch(url) for key,url in urls.items()}
    data = {key:json.loads(value) for key,value in contents.items()}
    validate_lxns(data['lxns_songs'])
    validate_cn(data['cn_maidata'])
    validate_aliases(data['lxns_aliases'],{s['id'] for s in data['lxns_songs']['songs']})
    old = json.loads((ROOT/'data/lxns_songs.json').read_bytes())
    if len(data['lxns_songs']['songs']) < len(old['songs'])*.9:
        raise ValueError('song count fell by more than 10%; review upstream changes manually')
    with tempfile.TemporaryDirectory(prefix='.staging-',dir=ROOT) as temp:
        stage = Path(temp)
        if not stage.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError('temporary staging path escapes pack root')
        shutil.copytree(ROOT/'corpus',stage/'corpus')
        (stage/'data').mkdir()
        for key,content in contents.items():
            (stage/'data'/f'{key}.json').write_bytes(content)
        stamp = datetime.now(timezone.utc).isoformat()
        provenance = json.loads((ROOT/'data/provenance.json').read_bytes())
        for source in provenance:
            if source['id'] in urls:
                source.update(url=urls[source['id']],retrieved_at=stamp)
                source.pop('commit',None)
                source.pop('note',None)
        (stage/'data/provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf-8')
        build(stage)
        if args.dry_run:
            print('Dry run passed; published files unchanged.')
            return
        # Stop the bot during publishing: a multi-file copy is not a DB transaction.
        for path in (ROOT/'corpus').glob('maimai_*/generated-*.md'):
            if not path.resolve().is_relative_to((ROOT/'corpus').resolve()):
                raise ValueError('generated path escapes corpus')
            path.unlink()
        shutil.copytree(stage/'corpus',ROOT/'corpus',dirs_exist_ok=True)
        shutil.copytree(stage/'data',ROOT/'data',dirs_exist_ok=True)
        shutil.copyfile(stage/'manifest.json',ROOT/'manifest.json')
    print('Published. Review differences, validate, then restart the bot.')


if __name__ == '__main__':
    main()
