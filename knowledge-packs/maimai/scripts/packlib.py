"""Shared, dependency-free snapshot validation and local lookup."""
from datetime import datetime, time, timezone, timedelta
from decimal import Decimal
import json
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
DIFFICULTIES = ('BASIC', 'ADVANCED', 'EXPERT', 'MASTER', 'Re:MASTER')
CN_KEYS = {'standard': ('lev_bas','lev_adv','lev_exp','lev_mas','lev_remas'),
           'dx': ('dx_lev_bas','dx_lev_adv','dx_lev_exp','dx_lev_mas','dx_lev_remas')}
NOTE_KEYS = ('tap','hold','slide','touch','break')


def normalize(value):
    return ''.join(unicodedata.normalize('NFKC', str(value)).casefold().split())


def validate_lxns(data):
    if not isinstance(data, dict) or not data.get('songs') or not data.get('versions'):
        raise ValueError('invalid public song list')
    seen = set()
    for song in data['songs']:
        if type(song['id']) is not int or song['id'] <= 0 or song['id'] in seen:
            raise ValueError('invalid/duplicate song ID')
        seen.add(song['id'])
        if not song.get('title') or not isinstance(song.get('difficulties'), dict):
            raise ValueError(f'missing song fields: {song["id"]}')
        if not any(song['difficulties'].values()):
            raise ValueError('song has no charts')
        for kind, charts in song['difficulties'].items():
            if kind not in ('standard','dx','utage'):
                raise ValueError(f'unknown chart type: {kind}')
            indices = set()
            for chart in charts:
                index = chart['difficulty']
                if type(index) is not int or not 0 <= index <= 4 or index in indices or chart['type'] != kind:
                    raise ValueError('duplicate/invalid chart index')
                indices.add(index)
                ds = Decimal(str(chart['level_value']))
                if not ds.is_finite() or not 0 <= ds <= 20 or (kind != 'utage' and ds == 0):
                    raise ValueError('invalid chart constant')
                if not isinstance(chart['level'], str) or not re.fullmatch(r'\d{1,2}\+?\??', chart['level']):
                    raise ValueError('invalid display level')
                if chart.get('release_date'):
                    datetime.strptime(chart['release_date'], '%Y-%m-%d')
                notes = chart.get('notes')
                if notes is not None:
                    sides = [notes['left'],notes['right']] if 'left' in notes and 'right' in notes else [notes]
                    for side in sides:
                        if any(type(side.get(k)) is not int or side[k] < 0 for k in (*NOTE_KEYS,'total')):
                            raise ValueError('invalid note counts')
                        if sum(side[k] for k in NOTE_KEYS) != side['total']:
                            raise ValueError('note total mismatch')
    return data


def validate_cn(data):
    if not isinstance(data, list) or not data:
        raise ValueError('invalid CN metadata list')
    seen = set()
    for song in data:
        key = normalize(song['title']), normalize(song['artist'])
        if key in seen or not any(song.get(k) for keys in CN_KEYS.values() for k in keys):
            raise ValueError('duplicate CN identity or no charts')
        seen.add(key)
    return data


def validate_aliases(data, song_ids):
    if not isinstance(data, dict) or not isinstance(data.get('aliases'), list):
        raise ValueError('invalid aliases response')
    seen = set()
    for item in data['aliases']:
        if type(item['song_id']) is not int or item['song_id'] <= 0 or item['song_id'] in seen:
            raise ValueError('duplicate/invalid alias song ID')
        seen.add(item['song_id'])
        if not isinstance(item['aliases'], list) or any(not isinstance(a, str) or len(a) > 300 for a in item['aliases']):
            raise ValueError('invalid aliases')
    return data


def release_open(chart, now=None):
    if not chart.get('release_date'):
        return True
    day = datetime.strptime(chart['release_date'], '%Y-%m-%d').date()
    instant = datetime.combine(day, time(7), timezone(timedelta(hours=8)))
    return (now or datetime.now(timezone.utc)) >= instant


def load_songs(root=ROOT):
    return json.loads((root/'data'/'songs.json').read_text(encoding='utf-8'))


def lookup(songs, query, limit=10):
    term = normalize(query)
    if not term or len(term) > 200:
        raise ValueError('query must contain 1..200 characters')
    exact = [s for s in songs if term in {str(s['id']),normalize(s['title']),
                                        *(normalize(a) for a in s.get('aliases', []))}]
    result = exact or [s for s in songs if term in normalize(s['title']) or term in normalize(s['artist'])
                      or any(term in normalize(a) for a in s.get('aliases', []))]
    return result[:max(1,min(50,limit))]
