"""Original offline examples. Rating profile: Diving-Fish source, 2026-08-18.

This is a community implementation profile, not a claim of SEGA source code.
All achievements use percentage units, e.g. 100.5, never 1.005 or 1005000.
"""
from decimal import Decimal, ROUND_FLOOR

# (inclusive lower bound, coefficient, display rank)
RATING_STEPS = tuple((Decimal(a), Decimal(c), rank) for a, c, rank in (
    ('0','0','D'), ('10','1.6','D'), ('20','3.2','D'), ('30','4.8','D'),
    ('40','6.4','D'), ('50','8.0','C'), ('60','9.6','B'), ('70','11.2','BB'),
    ('75','12.0','BBB'), ('79.9999','12.8','BBB'), ('80','13.6','A'),
    ('90','15.2','AA'), ('94','16.8','AAA'), ('96.9999','17.6','AAA'),
    ('97','20.0','S'), ('98','20.3','S+'), ('98.9999','20.6','S+'),
    ('99','20.8','SS'), ('99.5','21.1','SS+'), ('99.9999','21.4','SS+'),
    ('100','21.6','SSS'), ('100.4999','22.2','SSS'), ('100.5','22.4','SSS+'),
))


def number(value):
    if isinstance(value, bool):
        raise ValueError('boolean is not a numeric score')
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError('score must be finite')
    return result


def rating(ds, achievements):
    ds, achievements = number(ds), number(achievements)
    if not 0 < ds <= 20 or not 0 <= achievements <= 101:
        raise ValueError('expected constant (0,20], achievement [0,101]')
    coefficient, rank = next((c, r) for lower, c, r in reversed(RATING_STEPS) if achievements >= lower)
    value = ds * min(achievements, Decimal('100.5')) / 100 * coefficient
    return int(value.to_integral_value(rounding=ROUND_FLOOR)), rank


def dx_score(critical, perfect, great, good=0, miss=0):
    counts = critical, perfect, great, good, miss
    if any(type(n) is not int or n < 0 for n in counts):
        raise ValueError('judgment counts must be non-negative integers')
    return {'score': 3*critical + 2*perfect + great, 'maximum': 3*sum(counts)}


def achievement_loss(notes, kind, judgment):
    """Loss in percentage POINTS for one note, DX scoring with at least one break.

    Ordinary: perfect/great/good/miss. Break: critical/p50/p100/great1/
    great2/great3/good/miss. Inputs are disjoint note categories.
    """
    weights = {'tap': 500, 'touch': 500, 'hold': 1000, 'slide': 1500, 'break': 2500}
    if set(notes) != set(weights) or any(type(v) is not int or v < 0 for v in notes.values()):
        raise ValueError('expected tap/touch/hold/slide/break note counts')
    if kind not in weights or notes[kind] < 1 or notes['break'] < 1:
        raise ValueError('note absent, or zero-break scoring requires separate rules')
    maximum = sum(notes[k] * w for k, w in weights.items())
    if kind == 'break':
        base, bonus = {
            'critical': (2500, '1'), 'p50': (2500, '.75'), 'p100': (2500, '.5'),
            'great1': (2000, '.4'), 'great2': (1500, '.4'),
            'great3': (1250, '.4'), 'good': (1000, '.3'), 'miss': (0, '0')
        }[judgment]
        return Decimal(2500-base)*100/maximum + (1-Decimal(bonus))/notes['break']
    factor = {'perfect': Decimal(1), 'great': Decimal('.8'),
              'good': Decimal('.5'), 'miss': Decimal(0)}[judgment]
    return Decimal(weights[kind])*(1-factor)*100/maximum


def best50(records):
    """Input records must already be region/version eligible and authorized.

    Required keys: song_id, type, difficulty, ds, achievements, is_new.
    Duplicate chart records are collapsed before selecting pools.
    """
    charts = {}
    for record in records:
        if record['type'] == 'utage':
            continue
        if record['type'] not in ('standard', 'dx') or type(record['is_new']) is not bool:
            raise ValueError('invalid chart type or missing explicit pool flag')
        if type(record['difficulty']) is not int or not 0 <= record['difficulty'] <= 4:
            raise ValueError('invalid difficulty index')
        key = str(record['song_id']), record['type'], record['difficulty']
        ra, rank = rating(record['ds'], record['achievements'])
        item = dict(record, ra=ra, rank=rank)
        old = charts.get(key)
        if old is not None and old['is_new'] != item['is_new']:
            raise ValueError('conflicting new/old flags for one chart')
        if old is None or (ra, number(item['achievements'])) > (old['ra'], number(old['achievements'])):
            charts[key] = item
    order = lambda x: (-x['ra'], -number(x['ds']), -number(x['achievements']),
                       str(x['song_id']), x['type'], x['difficulty'])
    old = sorted((r for r in charts.values() if not r['is_new']), key=order)[:35]
    new = sorted((r for r in charts.values() if r['is_new']), key=order)[:15]
    return {'old': old, 'new': new, 'rating': sum(r['ra'] for r in old+new)}
