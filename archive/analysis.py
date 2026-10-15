"""원문을 바꾸지 않는 이동 창 집계와 반응 후보 계산."""

from collections import Counter, deque
import math
import re
import unicodedata

VERSION = 1
MAX_SECONDS = 7 * 24 * 3600
DEFAULTS = {'window_seconds': 10, 'min_messages': 5, 'burst_ratio': 3,
            'min_repeats': 3, 'repeat_share': .3}
JAMO = {ord(unicodedata.normalize('NFKC', chr(c))): chr(c) for c in range(0x3131, 0x314f)
        if len(unicodedata.normalize('NFKC', chr(c))) == 1}


def settings(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise ValueError('분석 설정 형식이 올바르지 않습니다')
    result = DEFAULTS | value
    for key, lower, upper in (('window_seconds', 5, 60), ('min_messages', 2, 1000),
                              ('min_repeats', 2, 1000), ('burst_ratio', 1.1, 20),
                              ('repeat_share', .05, 1)):
        number = result[key]
        if type(number) not in (int, float) or not math.isfinite(number) or not lower <= number <= upper:
            raise ValueError('분석 설정이 허용 범위를 벗어났습니다')
    if result['window_seconds'] not in (5, 10, 20, 30, 60):
        raise ValueError('분석 창은 5·10·20·30·60초 중에서 선택하세요')
    if any(type(result[k]) is not int for k in ('window_seconds', 'min_messages', 'min_repeats')):
        raise ValueError('시간과 최소 건수는 정수로 입력하세요')
    return result


def normalise(text):
    return unicodedata.normalize('NFKC', text).casefold().translate(JAMO)


def features(text):
    if not isinstance(text, str):
        return set(), Counter()
    value = re.sub(r'\{:[^{}]*:\}|https?://\S+', ' ', normalise(text))
    chars = Counter()
    # 공백으로 나눈 같은 자음도 한 반응이며 실제 자음 수는 따로 센다.
    for match in re.finditer(r'([ㄱ-ㅎ])(?:\s*\1)+', value):
        chars[('consonant', match[1] * 2)] += match[0].count(match[1])
    words = {('word', word) for word in re.findall(r'[가-힣]+|[a-z0-9_]{2,}', value)
             if not word.isdecimal()}
    return words | set(chars), chars


def analyze(rows, duration_ms, complete, options):
    options = settings(options)
    if type(duration_ms) not in (int, float) or not math.isfinite(duration_ms) or not 0 <= duration_ms <= MAX_SECONDS * 1000:
        raise ValueError('현재 분석은 길이 7일 이하의 VOD를 지원합니다')
    window = options['window_seconds']
    from .reaction_index import Scores
    scores = Scores(window)
    queue, terms, chars = deque(), Counter(), Counter()
    counts, bins = [0], Counter()
    candidates, latest = [], {}
    total = excluded = 0
    last_ms = -1
    iterator = iter(rows)
    pending = next(iterator, None)
    second = 1

    def record(kind, term, start, end, matching, ratio=None):
        key = (kind, term)
        share = matching / len(queue)
        rank = (matching, ratio if ratio is not None else share)
        item = latest.get(key)
        if item is not None and start <= item['end_ms']:
            item['end_ms'] = end
            if rank <= item['_rank']:
                return
        else:
            item = {'kind': kind, 'term': term, 'start_ms': start, 'end_ms': end}
            candidates.append(item)
            latest[key] = item
            if len(candidates) > 50000:
                raise ValueError('후보가 5만 개를 넘었습니다. 최소 건수나 비율을 높여 다시 분석하세요')
        matched = [entry for entry in queue if kind == 'burst' or key in entry[1]]
        peak_second = min(Counter(entry[0]['offset_ms'] // 1000 for entry in matched).items(), key=lambda pair: (-pair[1], pair[0]))[0]
        known = {entry[0].get('user_id_hash') for entry in matched if entry[0].get('user_id_hash')}
        item.update(_rank=rank, peak_ms=peak_second * 1000,
                    window_start_ms=start, window_end_ms=end,
                    messages=len(queue), matching_messages=matching, share=round(share, 4),
                    ratio=round(ratio, 3) if ratio is not None else None,
                    character_count=chars[key] if kind == 'consonant' else None,
                    known_authors=len(known), unknown_author_messages=sum(not entry[0].get('user_id_hash') for entry in matched),
                    top_terms=[{'term': key[1], 'messages': n} for key, n in terms.most_common(3)],
                    examples=[{'offset_ms': entry[0]['offset_ms'], 'nickname': entry[0].get('nickname'),
                               'text': (entry[0].get('text') or '')[:500]} for entry in matched[:3]])

    while pending is not None or (complete and second <= math.ceil(duration_ms / 1000)):
        if second > MAX_SECONDS:
            raise ValueError('현재 분석은 길이 7일 이하의 VOD를 지원합니다')
        added = 0
        while pending is not None and pending['offset_ms'] < second * 1000:
            text = pending.get('text')
            found, repeated = features(text)
            terms.update(found)
            chars.update(repeated)
            queue.append((pending, found, repeated))
            if len(queue) > 100000:
                raise ValueError('한 분석 창에 10만 건을 넘었습니다. 더 짧은 창으로 분석하세요')
            bins[pending['offset_ms'] // 10000] += 1
            last_ms = pending['offset_ms']
            total += 1
            excluded += not isinstance(text, str)
            added += 1
            pending = next(iterator, None)
        counts.append(counts[-1] + added)
        start = max(0, second - window)
        while queue and queue[0][0]['offset_ms'] < start * 1000:
            _, found, repeated = queue.popleft()
            terms.subtract(found)
            chars.subtract(repeated)
            for key in found:
                if terms[key] == 0:
                    del terms[key]
            for key in repeated:
                if chars[key] == 0:
                    del chars[key]
        known_end = max(duration_ms, last_ms + 1) if complete else last_ms + 1
        if second >= window and queue and (complete or pending is not None or second * 1000 <= known_end):
            count = len(queue)
            burst = False; eligible = set()
            if start >= 30:
                baseline_start = max(0, start - 60)
                reference = (counts[start] - counts[baseline_start]) * window / (start - baseline_start)
                ratio = count / max(1, reference)
                if count >= options['min_messages'] and ratio >= options['burst_ratio']:
                    record('burst', '', start * 1000, second * 1000, count, ratio)
                    burst = True
            for (kind, term), count in sorted(terms.items()):
                if count >= options['min_repeats'] and count / len(queue) >= options['repeat_share']:
                    record(kind, term, start * 1000, second * 1000, count)
                    eligible.add((kind, term))
            scores.add(queue, eligible, burst)
        second += 1
    known_end = max(duration_ms, last_ms + 1) if complete else max(0, last_ms + 1)
    display_end = max(duration_ms, known_end)
    graph = []
    for index in range(math.ceil(display_end / 10000)):
        start, end = index * 10000, min((index + 1) * 10000, display_end)
        graph.append({'start_ms': start, 'end_ms': end, 'messages': bins[index] if start < known_end else None,
                      'coverage': 'known' if end <= known_end else 'partial' if start < known_end else 'unknown'})
    for item in candidates:
        item.pop('_rank')
    candidates.sort(key=lambda item: (item['peak_ms'], item['kind'], item['term']))
    for index, item in enumerate(candidates):
        item['id'] = index
    return {'version': VERSION, 'settings': options, 'messages': total, 'excluded_text_messages': excluded,
            'known_until_ms': known_end, 'duration_ms': display_end, 'complete_source': complete,
            'baseline_insufficient_until_ms': min(known_end, (30 + window) * 1000),
            'graph': graph, 'candidates': candidates, 'reaction_index': scores.result()}
