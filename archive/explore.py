"""기존 결과만 읽는 공통 시간축·시간순 검색. 원본과 분석 상태에는 쓰지 않는다."""

from heapq import merge
import math

from . import analysis, analysis_store, speech_store, voice_store
from .storage import load_project, project_path

NAMES = {'burst': '채팅 급증', 'word': '반복 단어', 'consonant': '자음 반응'}
ERRORS = (ValueError, KeyError, OSError, TypeError, AttributeError)
MAX_MS = analysis.MAX_SECONDS * 1000


def options(query='', source='all', speaker='', start_ms=None, end_ms=None, cursor=0, chat_offset_ms=0):
    if (not isinstance(query, str) or len(query) > 200 or source not in ('all', 'chat', 'speech', 'reaction')
            or not isinstance(speaker, str) or len(speaker) > 100 or type(cursor) is not int or cursor < 0
            or type(chat_offset_ms) is not int or not -600000 <= chat_offset_ms <= 600000):
        raise ValueError('통합 검색 조건이 올바르지 않습니다')
    for value in (start_ms, end_ms):
        if value is not None and (type(value) is not int or not 0 <= value <= MAX_MS + 600000):
            raise ValueError('조회 시각이 허용 범위를 벗어났습니다')
    if start_ms is not None and end_ms is not None and start_ms >= end_ms:
        raise ValueError('끝 시각은 시작보다 뒤여야 합니다')


def timed(kind, row, start, end, at=None, offset=0):
    if any(type(v) is not int for v in (start, end)) or not 0 <= start <= end <= MAX_MS:
        raise ValueError('저장된 탐색 시각이 올바르지 않습니다')
    if at is None:
        at = start
    if type(at) is not int or not start <= at <= end:
        raise ValueError('저장된 반응 정점이 범위와 일치하지 않습니다')
    return row | {'kind': kind, 'raw_start_ms': start, 'raw_end_ms': end,
                  'start_ms': max(0, start + offset), 'end_ms': max(0, end + offset),
                  'at_ms': max(0, at + offset)}


def chat_note(data):
    task = data['tasks']['chat']
    labels = {'complete': '전체 제공 채팅', 'empty': '현재 제공 채팅 없음', 'unavailable': '채팅 미제공'}
    return labels.get(task['state'], '일부 수집 또는 채팅 준비 전')


def snapshot(path, data, offset):
    notes, reaction, speech = [chat_note(data)], [], []
    result, run, processed, complete = None, None, 0, False
    try:
        result = analysis_store.load(path, data)
        if result:
            for bin in result['graph']:
                if (any(type(bin[k]) is not int for k in ('start_ms', 'end_ms'))
                        or not 0 <= bin['start_ms'] < bin['end_ms'] <= MAX_MS
                        or bin['coverage'] not in ('known', 'partial', 'unknown')
                        or (bin['messages'] is not None and (type(bin['messages']) is not int or bin['messages'] < 0))):
                    raise ValueError('채팅 그래프 형식이 올바르지 않습니다')
            reaction = [timed('reaction', dict(id=str(r['id']), text=f"{NAMES[r['kind']]} {r['term']}",
                        detail=f"정점 창 {r['messages']}건 · " + ' / '.join(x['text'] or '' for x in r['examples'])),
                        r['start_ms'], r['end_ms'], r['peak_ms'], offset) for r in result['candidates']]
            if result.get('stale'):
                notes.append('반응: 지난 채팅 입력의 분석 결과')
            if not result.get('unavailable') and (not result.get('complete_source') or result.get('boundary_unverified')):
                notes.append('반응: 일부 자료 또는 경계 확인 필요')
        else:
            notes.append('반응 분석 결과 없음')
    except ERRORS:
        result = None
        notes.append('반응 분석 파일을 읽지 못했습니다')
    try:
        state = speech_store.view(path, data)
        run = speech_store.manifest(path)
        if run:
            edits = speech_store.corrections(path, run)
            rows = [r | {'text': edits.get(r['id'], r['text']), 'corrected': r['id'] in edits}
                    for r in speech_store.segments(path, run)]
            try:
                voice = voice_store.result(path)
                if voice and (voice['transcript_run'] != run['id'] or not voice_store.current(path, voice)):
                    notes.append('화자: 현재 전사와 맞지 않아 배정 제외')
                elif voice:
                    rows = voice_store.decorate(path, run['id'], rows)
                else:
                    notes.append('화자 분석 결과 없음')
            except ERRORS:
                notes.append('화자 파일을 읽지 못했습니다. 전사만 표시합니다')
            speech = [timed('speech', r, r['start_ms'], r['end_ms']) for r in rows]
            processed, complete = run['processed_ms'], run['complete']
            notes.append('전사 전체 범위 처리 · 정확도 확인 필요' if complete else '전사 일부 범위 처리')
            if state['stale']:
                notes.append('전사: 지난 영상 입력의 결과')
        else:
            notes.append('전사 결과 없음')
    except ERRORS:
        run = None
        notes.append('전사 파일을 읽지 못했습니다')
    return {'notes': notes, 'reaction': reaction, 'speech': speech, 'analysis': result,
            'processed_ms': processed, 'complete': complete}


def info(root, vod, chat_offset_ms=0):
    options(chat_offset_ms=chat_offset_ms)
    path = project_path(root, vod)
    data = load_project(path, vod)
    saved = snapshot(path, data, chat_offset_ms)
    duration = data['tasks']['video'].get('verification', {}).get('duration', data['metadata'].get('duration') or 0)
    if type(duration) not in (int, float) or not math.isfinite(duration) or not 0 <= duration <= analysis.MAX_SECONDS:
        raise ValueError('영상 길이를 확인할 수 없습니다')
    video_ms = round(duration * 1000)
    result = saved['analysis']
    tracks = [{k: r.get(k) for k in ('start_ms', 'end_ms', 'speaker', 'speaker_name', 'status')} for r in saved['speech']]
    speakers = {r['speaker']: r['speaker_name'] for r in saved['speech'] if r.get('speaker')}
    extent = max([video_ms, 1, saved['processed_ms'],
                  max(0, (data['tasks']['chat'].get('progress', {}).get('last_ms') or 0) + chat_offset_ms + 1)]
                 + [r['end_ms'] for r in saved['reaction'] + saved['speech']])
    if data.get('input'): extent = max(video_ms, 1)
    return {'notes': saved['notes'], 'duration_ms': extent, 'video_ms': video_ms, 'speakers': speakers,
            'tracks': tracks, 'reactions': saved['reaction'], 'graph': result['graph'] if result else [],
            'chat_offset_ms': chat_offset_ms, 'processed_ms': saved['processed_ms'], 'complete': saved['complete'],
            'boundary_unverified': bool(result and result.get('boundary_unverified'))}


def search(root, vod, **values):
    defaults = dict(query='', source='all', speaker='', start_ms=None, end_ms=None, cursor=0, chat_offset_ms=0)
    if values.keys() - defaults.keys():
        raise ValueError('알 수 없는 통합 검색 조건입니다')
    args = defaults | values
    options(**args)
    path = project_path(root, vod)
    data = load_project(path, vod)
    saved = snapshot(path, data, args['chat_offset_ms'])
    needle = analysis.normalise(args['query'])

    def chats():
        for index, row in enumerate(analysis_store.rows(path, data, mapping_offset=args['chat_offset_ms'])):
            yield timed('chat', {'id': str(index), 'text': row.get('text') or '(본문 없음)', 'nickname': row.get('nickname')},
                        row['offset_ms'], row['offset_ms'], offset=args['chat_offset_ms'])

    def matches(row):
        start, end = args['start_ms'], args['end_ms']
        # 점인 채팅은 [시작, 끝), 구간인 발언/반응은 겹치는 전체 행을 표시한다.
        if start is not None and (row['end_ms'] < start or (row['end_ms'] == start and row['start_ms'] < start)):
            return False
        if end is not None and row['start_ms'] >= end:
            return False
        if row['kind'] == 'speech' and args['speaker']:
            if args['speaker'] == 'failed':
                if row.get('status') != 'failed':
                    return False
            elif args['speaker'] == 'unassigned':
                if 'speaker_run' in row:
                    return False
            elif row.get('speaker') != args['speaker']:
                return False
        text = ' '.join(str(row.get(k) or '') for k in ('text', 'nickname', 'speaker_name', 'speaker_reason', 'detail'))
        return needle in analysis.normalise(text)

    order = lambda row: (row['at_ms'], row['kind'])
    lists = [sorted(saved[kind], key=order) for kind in ('reaction', 'speech') if args['source'] in ('all', kind)]
    # shortcut: 채팅을 순차 읽는다. 대규모 검색이 느려지면 원본과 분리된 색인을 추가한다.
    def page(streams):
        items, total = [], 0
        for row in merge(*streams, key=order):
            if matches(row):
                if args['cursor'] <= total < args['cursor'] + 100:
                    items.append(row)
                total += 1
        return {'items': items, 'total': total, 'next_cursor': args['cursor'] + 100 if total > args['cursor'] + 100 else None,
                'notes': saved['notes']}

    if args['source'] in ('all', 'chat') and data['tasks']['chat']['assets'].get('jsonl'):
        try:
            # JSONL은 시각 순서이며 같은 시각의 원문 순서도 보존한다.
            return page(lists + [chats()])
        except ERRORS:
            saved['notes'].append('채팅 파일을 읽지 못했습니다. 채팅 검색 결과는 제외했습니다')
    return page(lists)
