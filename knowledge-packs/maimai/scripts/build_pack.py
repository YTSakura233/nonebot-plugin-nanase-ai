"""Rebuild song documents and indexes from checked-in metadata, fully offline."""
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
import hashlib
import json

from packlib import (ROOT, CN_KEYS, DIFFICULTIES, NOTE_KEYS, normalize, release_open,
                     validate_aliases, validate_cn, validate_lxns)


def json_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def text_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip()+'\n', encoding='utf-8')


def clean(value):
    return str(value).replace('|','／').replace('\r',' ').replace('\n',' ').replace('<','＜').replace('>','＞')


def cn_match(song, index):
    key = normalize('Link' if song['title'] == 'Link(CoF)' else song['title'])
    options = index.get(key, [])
    if len(options) == 1 and song['title'] != 'Link(CoF)':
        return options[0], 'unique_title'
    exact = [item for item in options if normalize(item['artist']) == normalize(song['artist'])]
    return (exact[0], 'title_artist') if len(exact) == 1 else (None, 'unmatched_or_ambiguous')


def notes_text(notes):
    if not notes:
        return '物量未提供'
    if 'left' in notes:
        return 'BUDDY左侧 '+notes_text(notes['left'])+'；右侧 '+notes_text(notes['right'])
    return ' / '.join(f'{name}={notes[key]}' for key,name in
        zip(NOTE_KEYS,('TAP','HOLD','SLIDE','TOUCH','BREAK'))) + f'；总物量={notes["total"]}，DX理论分={3*notes["total"]}'


def song_block(song, snapshot_day):
    title, sid = clean(song['title']), song['id']
    lines = [f'## {title}｜落雪歌曲ID {sid}',
        f'范围：国服资料快照 {snapshot_day}；来源：落雪公开曲库，社区定数。',
        f'艺术家：{clean(song["artist"])}；分类：{clean(song["genre"])}；BPM：{song["bpm"]}。',
        f'曲目首次版本：{clean(song["version_name"])}（{song["version"]}）；最早配信日期：{song.get("release_date") or "未知"}。',
        f'歌曲别名（社区，多义词须消歧）：{clean("、".join(song["aliases"])) or "未收录"}。',
        f'国服NET社区快照：{song["cn_match_status"]}；disabled={str(song.get("disabled",False)).lower()}。']
    for chart in song['charts']:
        kind = chart['type']
        diff = DIFFICULTIES[chart['difficulty']] if kind != 'utage' else 'UTAGE'
        label = '标准谱SD' if kind == 'standard' else 'DX谱' if kind == 'dx' else '宴会场'
        name = f'{title} {label} {diff}（ID {sid}）'
        lines += [f'### {name}', f'{name}：落雪显示等级 {chart["level"]}；'+
            ('不提供常规Rating定数，排除B50。' if kind == 'utage' else f'社区定数 {chart["level_value"]}。')]
        if chart.get('cn_level'):
            lines += [f'{name}：国服NET社区快照显示 {chart["cn_level"]}；'+
                ('两源显示等级一致。' if chart['cn_level'] == chart['level'] else '两源存在差异；回答国服显示等级时说明此差异，不能把落雪定数当作已核实的国服当前定数。')]
        elif kind != 'utage':
            lines += [f'{name}：未在另一份国服快照中匹配该谱面；不能据此断言已删曲。']
        lines += [f'{name}：谱师 {clean(chart.get("note_designer") or "未提供")}；谱面版本 {chart["version_name"]}；配信 {chart.get("release_date") or "未知"}。',
                  f'{name}：{notes_text(chart.get("notes"))}。',
                  f'{name}：按快照采集时刻的配信条件为 {"日期已到或未知" if chart["release_open_at_snapshot"] else "尚未配信"}；实际解锁需另查。']
        if kind == 'utage':
            lines += [f'{name}：宴标 {clean(chart.get("kanji",""))}；BUDDY={chart.get("is_buddy",False)}；描述 {clean(chart.get("description",""))}。']
    lines += ['数据核对：https://maimai.lxns.net/docs/api/maimai ｜ https://maimai-net.cn/database', '']
    return '\n'.join(lines)


def build(root=ROOT):
    raw = validate_lxns(json.loads((root/'data/lxns_songs.json').read_bytes()))
    cn = validate_cn(json.loads((root/'data/cn_maidata.json').read_bytes()))
    aliases = validate_aliases(json.loads((root/'data/lxns_aliases.json').read_bytes()), {s['id'] for s in raw['songs']})
    provenance = json.loads((root/'data/provenance.json').read_bytes())
    observed = next(p['retrieved_at'] for p in provenance if p['id'] == 'lxns_songs')
    instant = datetime.fromisoformat(observed.replace(' UTC','+00:00'))
    snapshot_day = instant.date().isoformat()
    versions = {v['version']:v['title'] for v in raw['versions']}
    cn_index = defaultdict(list)
    for item in cn:
        cn_index[normalize(item['title'])].append(item)
    alias_map = {a['song_id']:a['aliases'] for a in aliases['aliases']}
    songs, discrepancies, level_index = [], [], defaultdict(list)
    for source in sorted(raw['songs'], key=lambda item:item['id']):
        song = dict(source)
        song['aliases'] = alias_map.get(song['id'], [])
        song['version_name'] = versions.get(song['version'], f'版本号 {song["version"]}')
        matched, status = cn_match(song, cn_index)
        song['cn_match_status'] = status
        song['cn_title'] = matched['title'] if matched else None
        song['cn_artist'] = matched['artist'] if matched else None
        song['cn_version'] = matched.get('version') if matched else None
        song['charts'] = []
        for kind, charts in song.pop('difficulties').items():
            for source_chart in charts:
                chart = dict(source_chart)
                version = chart.get('version',song['version'])
                chart['version_name'] = versions.get(version, f'版本号 {version}')
                chart['release_open_at_snapshot'] = release_open(chart, instant)
                chart['cn_level'] = matched.get(CN_KEYS[kind][chart['difficulty']]) if matched and kind in CN_KEYS else None
                song['charts'].append(chart)
                if chart['cn_level'] and chart['cn_level'] != chart['level']:
                    discrepancies.append({'song_id':song['id'],'title':song['title'],'type':kind,
                        'difficulty':chart['difficulty'],'lxns_level':chart['level'],
                        'cn_level':chart['cn_level'],'lxns_constant':chart['level_value']})
                if kind != 'utage':
                    entry = {'song_id':song['id'],'title':song['title'],'artist':song['artist'],
                        'type':kind,'difficulty':chart['difficulty'],'level':chart['level'],
                        'constant':chart['level_value'],'cn_level':chart['cn_level'],
                        'disabled':bool(song.get('disabled')),'release_open_at_snapshot':chart['release_open_at_snapshot']}
                    level_index[chart['level']].append(entry)
        songs.append(song)
    json_write(root/'data/songs.json', songs)
    json_write(root/'data/level_index.json', dict(sorted(level_index.items())))
    json_write(root/'data/discrepancies.json', discrepancies)
    cn_level_index = defaultdict(list)
    for item in cn:
        matched_ids = [s['id'] for s in songs if s['cn_title'] == item['title'] and s['cn_artist'] == item['artist']]
        for kind, keys in CN_KEYS.items():
            for diff, key in enumerate(keys):
                if item.get(key):
                    cn_level_index[item[key]].append({'title':item['title'],'artist':item['artist'],
                        'type':kind,'difficulty':diff,'level':item[key],
                        'matched_lxns_ids':matched_ids,'version':item.get('version')})
    json_write(root/'data/cn_level_index.json',dict(sorted(cn_level_index.items())))
    for collection in ('maimai_songs','maimai_levels'):
        folder = root/'corpus'/collection
        folder.mkdir(parents=True, exist_ok=True)
        for file in folder.glob('generated-*.md'):
            if not file.resolve().is_relative_to(folder.resolve()):
                raise ValueError('generated path escapes corpus')
            file.unlink()
    shard_size = 32
    for offset in range(0,len(songs),shard_size):
        group = songs[offset:offset+shard_size]
        title = f'# 国服歌曲资料 {offset//shard_size+1:03d}｜ID {group[0]["id"]}—{group[-1]["id"]}\n\n'
        text_write(root/f'corpus/maimai_songs/generated-songs-{offset//shard_size+1:03d}.md',
                   title+'\n'.join(song_block(s,snapshot_day) for s in group))
    for level, entries in level_index.items():
        entries.sort(key=lambda r:(Decimal(str(r['constant'])),r['song_id'],r['type'],r['difficulty']))
        header = f'# 等级 {level} 的常规谱面索引\n\n国服社区快照 {snapshot_day}；分组依据落雪显示等级，不含宴会场。\n每行保留曲名、类型、难度和来源；两源等级不同已标明。disabled/未配信不代表可游玩。\n\n'
        lines = []
        for r in entries:
            flags = []
            if r['disabled']: flags.append('disabled')
            if not r['release_open_at_snapshot']: flags.append('未配信')
            flags.append(f'国服NET显示{r["cn_level"]}' if r['cn_level'] else '未匹配NET快照')
            lines.append(f'- 等级{level}｜{clean(r["title"])}｜{clean(r["artist"])}｜{r["type"]} {DIFFICULTIES[r["difficulty"]]}｜落雪ID {r["song_id"]}｜社区定数 {r["constant"]}｜{"；".join(flags)}。')
        text_write(root/f'corpus/maimai_levels/generated-lxns-level-{level.replace("+","plus")}.md', header+'\n'.join(lines))
    for level,entries in cn_level_index.items():
        header = f'# 国服NET快照显示等级 {level} 索引\n\n来源：CrazyKidCN国服NET社区快照；快照采集 {snapshot_day}。\n本表按国服NET观察等级分组，不使用落雪等级代替；不含宴会场。\n\n'
        lines = [f'- 国服NET等级{level}｜{clean(r["title"])}｜{clean(r["artist"])}｜{r["type"]} {DIFFICULTIES[r["difficulty"]]}｜关联落雪ID {r["matched_lxns_ids"] or "未匹配"}｜版本 {clean(r["version"])}。' for r in entries]
        text_write(root/f'corpus/maimai_levels/generated-cn-level-{level.replace("+","plus")}.md',header+'\n'.join(lines))
    stats = {'songs':len(songs),'charts':sum(len(s['charts']) for s in songs),
        'chart_types':dict(Counter(c['type'] for s in songs for c in s['charts'])),
        'cn_records':len(cn),'cn_charts':sum(len(v) for v in cn_level_index.values()),'alias_records':len(aliases['aliases']),
        'aliases_attached':sum(len(s['aliases']) for s in songs),
        'alias_ids_absent_from_song_snapshot':sorted(set(alias_map)-{s['id'] for s in songs}),
        'level_discrepancies':len(discrepancies),'disabled_songs':sum(bool(s.get('disabled')) for s in songs),
        'unreleased_charts_at_snapshot':sum(not c['release_open_at_snapshot'] for s in songs for c in s['charts']),
        'cn_unmatched_regular_songs':sum(s['cn_match_status']=='unmatched_or_ambiguous' and any(c['type']!='utage' for c in s['charts']) for s in songs),
        'snapshot_time_utc':observed}
    text_write(root/'corpus/maimai_songs/generated-overview.md', '# 曲库快照统计与读法\n\n'+
        '\n'.join(f'- {k}: {v}' for k,v in stats.items()) +
        '\n\n落雪歌曲ID合并标准和DX，曲目条数不是谱面数。数据源不是官方完整曲库或当前解锁清单。\n'+
        '定数来自落雪社区资料；国服NET快照只有显示等级，不用于凭空补小数定数。\n'+
        '两源显示等级差异见 data/discrepancies.json。别名中未在歌曲快照出现的ID不新增虚构歌曲。\n'+
        '来源：https://maimai.lxns.net/docs/api/maimai 与 https://maimai-net.cn/database 。')
    files = sorted((root/'corpus').rglob('*.md'))
    if len(files) > 200:
        raise ValueError('corpus exceeds plugin limit of 200 documents')
    total_chunks = sum(len(range(0,len(p.read_text(encoding='utf-8')),1080)) for p in files)
    if total_chunks > 20000 or any(p.stat().st_size>4*1024*1024 for p in files):
        raise ValueError('corpus exceeds plugin size limits')
    stats['documents'] = len(files)
    stats['chunks_1200_overlap_120'] = total_chunks
    toc = ['# 舞萌知识库完整目录', '', '曲库快照：2026-11-01；安装说明更新：2026-11-02。原始快照、代码和部署说明见 [README](README.md)。', '']
    for folder in sorted((root/'corpus').iterdir()):
        if folder.is_dir():
            toc += [f'## {folder.name}', '']
            for path in sorted(folder.glob('*.md')):
                title = path.read_text(encoding='utf-8').splitlines()[0].lstrip('# ')
                toc.append(f'- [{title}]({path.relative_to(root).as_posix()})')
            toc.append('')
    text_write(root/'INDEX.md','\n'.join(toc))
    records = {}
    for path in sorted((root/'data').glob('*.json'))+files:
        content = path.read_bytes()
        records[path.relative_to(root).as_posix()] = {'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}
    manifest = {'pack_version':'1.0.2','checked_on':'2026-11-02','statistics':stats,
                'sources':provenance,'files':records}
    json_write(root/'manifest.json',manifest)
    print(json.dumps(stats,ensure_ascii=False,indent=2))
    return manifest


if __name__ == '__main__':
    build()
