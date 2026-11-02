"""Validate a release without database, network, QQ or LLM access."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil
import io
from contextlib import redirect_stdout
import unittest
from unittest.mock import patch

from packlib import ROOT, CN_KEYS, load_songs, lookup, normalize, release_open, validate_lxns, validate_cn, validate_aliases
sys.path.insert(0,str(ROOT/'examples'))
from maimai_math import rating, best50, achievement_loss, dx_score
from simai_timing import timeline


class PackChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT/'manifest.json').read_bytes())
        cls.raw = validate_lxns(json.loads((ROOT/'data/lxns_songs.json').read_bytes()))
        cls.cn = validate_cn(json.loads((ROOT/'data/cn_maidata.json').read_bytes()))
        cls.songs = load_songs()

    def test_checksums(self):
        for relative, expected in self.manifest['files'].items():
            with self.subTest(file=relative):
                path = ROOT/relative
                self.assertTrue(path.resolve().is_relative_to(ROOT.resolve()))
                data = path.read_bytes()
                self.assertEqual(len(data),expected['bytes'])
                self.assertEqual(hashlib.sha256(data).hexdigest(),expected['sha256'])

    def test_corpus_limits(self):
        files = list((ROOT/'corpus').rglob('*.md'))
        self.assertLessEqual(len(files),200)
        self.assertGreaterEqual(len(list((ROOT/'corpus/maimai_game').glob('*.md'))),26)
        self.assertGreaterEqual(len(list((ROOT/'corpus/maimai_dev').glob('*.md'))),12)
        chunks = 0
        for path in files:
            self.assertLessEqual(path.stat().st_size,4*1024*1024)
            text = path.read_text(encoding='utf-8')
            self.assertTrue(text.strip())
            chunks += len(range(0,len(text),1080))
        self.assertLessEqual(chunks,20000)
        self.assertEqual(chunks,self.manifest['statistics']['chunks_1200_overlap_120'])

    def test_song_and_chart_coverage(self):
        self.assertEqual({s['id'] for s in self.songs},{s['id'] for s in self.raw['songs']})
        original = {(s['id'],kind,c['difficulty']) for s in self.raw['songs'] for kind,v in s['difficulties'].items() for c in v}
        generated = {(s['id'],c['type'],c['difficulty']) for s in self.songs for c in s['charts']}
        self.assertEqual(original,generated)
        self.assertEqual(len(generated),sum(len(s['charts']) for s in self.songs))

    def test_aliases_and_exact_lookup(self):
        aliases = validate_aliases(json.loads((ROOT/'data/lxns_aliases.json').read_bytes()),{s['id'] for s in self.songs})
        self.assertEqual(lookup(self.songs,'真爱歌')[0]['id'],8)
        self.assertEqual(lookup(self.songs,'8')[0]['id'],8)
        self.assertEqual(lookup(self.songs,' True Love Song ')[0]['id'],8)
        for bad in ('',' '*5,'x'*201):
            with self.assertRaises(ValueError):lookup(self.songs,bad)
        unknown = set(a['song_id'] for a in aliases['aliases'])-{s['id'] for s in self.songs}
        self.assertEqual(sorted(unknown),self.manifest['statistics']['alias_ids_absent_from_song_snapshot'])

    def test_homonyms_not_merged(self):
        link = [s for s in self.cn if s['title']=='Link']
        self.assertEqual(len(link),2)
        self.assertEqual(len({normalize(s['artist']) for s in link}),2)
        canonical = [s for s in self.songs if s['cn_title']=='Link']
        self.assertEqual(len(canonical),2)
        self.assertEqual(len({s['cn_artist'] for s in canonical}),2)

    def test_two_level_indexes(self):
        lxns = json.loads((ROOT/'data/level_index.json').read_bytes())
        cn = json.loads((ROOT/'data/cn_level_index.json').read_bytes())
        self.assertEqual(sum(map(len,lxns.values())),sum(c['type']!='utage' for s in self.songs for c in s['charts']))
        expected = sum(bool(s.get(k)) for s in self.cn for keys in CN_KEYS.values() for k in keys)
        self.assertEqual(sum(map(len,cn.values())),expected)
        for level,entries in lxns.items():
            self.assertTrue(all(e['level']==level for e in entries))
        for level,entries in cn.items():
            self.assertTrue(all(e['level']==level for e in entries))
        self.assertNotEqual(lxns['12'],lxns['12+'])

    def test_buddy_sides(self):
        buddies = [c for s in self.songs for c in s['charts'] if c.get('is_buddy')]
        self.assertTrue(buddies)
        self.assertTrue(all('left' in c['notes'] and 'right' in c['notes'] for c in buddies))

    def test_release_boundary(self):
        chart={'release_date':'2026-11-11'}
        self.assertFalse(release_open(chart,datetime(2026,11,10,22,59,59,tzinfo=timezone.utc)))
        self.assertTrue(release_open(chart,datetime(2026,11,10,23,0,tzinfo=timezone.utc)))

    def test_malformed_source_rejected(self):
        source=deepcopy(self.raw)
        source['songs'].append(deepcopy(source['songs'][0]))
        with self.assertRaises(ValueError):validate_lxns(source)
        source=deepcopy(self.raw)
        source['songs'][0]['difficulties']['standard'][0]['notes']['total']+=1
        with self.assertRaises(ValueError):validate_lxns(source)

    def test_rating_known_boundaries(self):
        self.assertEqual(rating('13.7','100.5'),(308,'SSS+'))
        self.assertEqual(rating('14','100'),(302,'SSS'))
        self.assertEqual(rating('14','100.4999'),(312,'SSS'))
        self.assertEqual(rating('14','100.5'),(315,'SSS+'))
        self.assertEqual(rating('14','101'),(315,'SSS+'))
        self.assertEqual(rating('14','99.9999'),(299,'SS+'))
        self.assertEqual(rating('14','97')[1],'S')
        for ds,acc in [('NaN','100'),('14','Infinity'),('0','100'),('14','1005000'),('14','-1')]:
            with self.assertRaises(ValueError):rating(ds,acc)

    def test_best50_pools_and_duplicate(self):
        records=[dict(song_id=i,type='dx',difficulty=3,ds='14',achievements='100.5',is_new=False) for i in range(1,41)]
        records += [dict(song_id=i,type='standard',difficulty=3,ds='13',achievements='100.5',is_new=True) for i in range(41,61)]
        records += [dict(records[0]),dict(song_id=100001,type='utage',difficulty=0,ds=0,achievements=101,is_new=True)]
        result=best50(records)
        self.assertEqual((len(result['old']),len(result['new']),result['rating']),(35,15,15405))
        self.assertTrue(all(r['type']=='dx' for r in result['old']))
        self.assertEqual(best50([])['rating'],0)
        with self.assertRaises(ValueError):best50([records[0],dict(records[0],is_new=True)])

    def test_dx_and_break_loss(self):
        self.assertEqual(dx_score(450,40,8,1,1),{'score':1438,'maximum':1500})
        notes=dict(tap=100,hold=10,slide=10,touch=20,**{'break':5})
        self.assertEqual(str(achievement_loss(notes,'break','p50')),'0.05')
        self.assertEqual(str(achievement_loss(notes,'break','p100')),'0.1')
        with self.assertRaises(ValueError):achievement_loss(dict(notes,**{'break':0}),'tap','miss')

    def test_simai_time_axis(self):
        data=timeline('(120){4}1,2/3,,(240)4,E')
        self.assertEqual([(float(e['time']),e['position']) for e in data['events']],[(0,1),(.5,2),(.5,3),(1.5,4)])
        self.assertEqual(float(data['end']),1.75)
        for bad in ('(0){4}1,E','(120){0}1,E','(120){4}1h[4:1],E','(120){4}1,','(120){4}1,E,2'):
            with self.assertRaises(ValueError):timeline(bad)

    def test_cli_exact_level(self):
        result=subprocess.run([sys.executable,str(ROOT/'scripts/lookup.py'),'--level','12','--limit','3'],capture_output=True,check=True)
        self.assertTrue(all(r['level']=='12' for r in json.loads(result.stdout)))

    def test_refresh_dry_run_and_invalid_source_preserve_files(self):
        import refresh
        with tempfile.TemporaryDirectory(prefix='.staging-test-',dir=ROOT) as temporary:
            root=Path(temporary)
            self.assertTrue(root.resolve().is_relative_to(ROOT.resolve()))
            shutil.copytree(ROOT/'data',root/'data')
            shutil.copytree(ROOT/'corpus',root/'corpus')
            before={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in root.rglob('*') if p.is_file()}
            contents={key:(root/'data'/f'{key}.json').read_bytes() for key in refresh.SOURCES}
            def fake_fetch(url):
                return next(contents[key] for key,template in refresh.SOURCES.items()
                            if url==template.format(version=25500))
            with patch.object(refresh,'ROOT',root),patch.object(refresh,'fetch',side_effect=fake_fetch), \
                 patch.object(sys,'argv',['refresh.py','--dry-run']),redirect_stdout(io.StringIO()):
                refresh.main()
            after={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in root.rglob('*') if p.is_file()}
            self.assertEqual(before,after)
            with patch.object(refresh,'ROOT',root),patch.object(refresh,'fetch',return_value=b'{}'), \
                 patch.object(sys,'argv',['refresh.py']),self.assertRaises(ValueError):
                refresh.main()
            self.assertEqual(before,{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in root.rglob('*') if p.is_file()})


if __name__=='__main__':
    unittest.main(verbosity=2)
