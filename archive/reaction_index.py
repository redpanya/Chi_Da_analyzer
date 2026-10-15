"""고정 길이 반응 창의 강도를 메시지 시각에 연결한 VOD 내부 상대 지수."""
import math
from functools import lru_cache
from pathlib import Path
from .storage import read_json

REVISION = 1


class Scores:
    def __init__(self, window):
        self.window = window
        self.points = {}

    def add(self, entries, terms, burst):
        if not burst and not terms: return
        # 같은 행이 여러 반응 조건에 걸려도 한 번만 집계한다.
        matched = [row['offset_ms'] for row, found, _ in entries if burst or found.intersection(terms)]
        rate = len(matched) / self.window
        for at in set(matched):
            self.points[at] = max(self.points.get(at, 0), rate)

    def result(self):
        values = list(self.points.values())
        low, high = (min(values), max(values)) if values else (0, 0)
        return {'revision': REVISION, 'window_seconds': self.window, 'min': low, 'max': high,
                'comparable': high > low, 'unit': 'matched_messages_per_second',
                'points': [{'at_ms': at, 'strength': rate,
                            'index': 1 + math.floor(9 * (rate-low)/(high-low) + .5) if high > low else 1}
                           for at, rate in sorted(self.points.items())]}


@lru_cache(maxsize=4)
def _snapshot(file, mtime, size, options, duration, complete):
    from .analysis import analyze
    source = read_json(Path(file))
    return analyze(source['chat'], duration, complete, dict(options))['reaction_index']


def with_snapshot(result, folder):
    """과거 요약 파일은 그대로 두고 저장 당시 채팅으로 표시용 지수만 계산한다."""
    analysis = result.get('reaction_analysis')
    if result.get('stale') or not analysis or analysis.get('reaction_index'): return result
    file = folder / 'source.json'
    if not file.exists() or file.is_symlink(): return result
    try:
        stat = file.stat()
        score = _snapshot(str(file), stat.st_mtime_ns, stat.st_size,
                          tuple(sorted(analysis['settings'].items())), analysis['duration_ms'], analysis['complete_source'])
    except (OSError, ValueError, KeyError, TypeError):
        return result
    return result | {'reaction_analysis': analysis | {'reaction_index': score}}
