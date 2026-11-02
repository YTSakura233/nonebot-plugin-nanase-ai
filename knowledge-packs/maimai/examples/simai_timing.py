"""A deliberately small TAP/EACH time-axis demonstrator, NOT a full simai parser."""
from fractions import Fraction
import re

DIRECTIVE = re.compile(r'^(?:\((\d{1,6}(?:\.\d{1,6})?)\)|\{(\d{1,6})\})')


def timeline(body: str, first='0'):
    if len(body)>10000:
        raise ValueError('demo chart exceeds 10000 characters')
    text = ''.join(body.split())
    time = Fraction(first)
    bpm = divisor = None
    events = []
    fragments = text.split(',')
    ended = False
    for index, fragment in enumerate(fragments):
        if fragment == 'E':
            if any(fragments[index+1:]):
                raise ValueError('content follows E')
            ended = True
            break
        while match := DIRECTIVE.match(fragment):
            if match[1] is not None:
                bpm = Fraction(match[1])
                if bpm <= 0: raise ValueError('BPM must be positive')
            else:
                if bpm is None: raise ValueError('BPM must precede divider')
                divisor = int(match[2])
                if divisor <= 0: raise ValueError('divider must be positive')
            fragment = fragment[match.end():]
        if bpm is None or divisor is None:
            raise ValueError('set BPM and divider before chart data')
        if fragment:
            if not re.fullmatch(r'[1-8](?:/[1-8])*',fragment):
                raise ValueError('demo supports TAP and slash-EACH only')
            positions = [int(p) for p in fragment.split('/')]
            if len(positions) != len(set(positions)):
                raise ValueError('duplicate simultaneous TAP')
            events.extend({'time':time,'position':p} for p in positions)
        time += Fraction(240,1)/bpm/divisor
    if not ended:
        raise ValueError('missing E')
    return {'events':events,'end':time}


if __name__ == '__main__':
    data = timeline('(120){4}1,2/3,,(240)4,E')
    for event in data['events']:
        print(f'{float(event["time"]):.6f}s: TAP {event["position"]}')
    print('End:',float(data['end']))
