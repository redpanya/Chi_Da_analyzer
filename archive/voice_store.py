"""원 전사와 분리된 화자 버전, 이름·교정 및 내보내기."""
import copy
import csv
import uuid
from collections import defaultdict

from .storage import Conflict, read_json, save_json, stamp
from . import task_timing

REASONS = {'no_voice': '연결할 음성 없음', 'short': '음성 근거 부족', 'mixed': '여러 화자 또는 동시발화',
           'ambiguous': '비슷한 목소리·배정 불확실', 'manual': '사용자 검토에서 실패 지정'}


def local(path, relative):
    base = path / 'voices'
    target = base / relative
    if not target.resolve().is_relative_to(base.resolve()):
        raise ValueError('화자 자료 경로가 올바르지 않습니다')
    for parent in [target, *target.parents]:
        if parent == path:
            break
        if parent.is_symlink():
            raise Conflict('화자 자료의 연결 파일은 지원하지 않습니다')
    return target


def state(path):
    file = local(path, 'state.json')
    return read_json(file) if file.exists() else {'state': 'idle', 'message': 'M3 음성 추출과 전사를 먼저 준비하세요', 'runs': [], 'stems': []}


def update(path, **values):
    value = task_timing.update(state(path), values) | {'updated_at': stamp()}
    save_json(local(path, 'state.json'), value)
    return value


def result(path, run=None):
    s = state(path)
    run = run or s.get('run')
    if not run:
        return None
    if run not in s.get('runs', []):
        raise ValueError('저장된 화자 분석 버전이 아닙니다')
    return read_json(local(path, f'runs/{run}/result.json'))


def edits(path, run):
    file = local(path, f'runs/{run}/edits.json')
    return read_json(file) if file.exists() else {'revision': 0, 'names': {}, 'assignments': {}, 'speakers': {}, 'history': []}


def current(path, r):
    from . import speech_store, speech_media
    from .storage import load_project
    s = speech_store.state(path)
    audio = s.get('audio')
    return bool(audio and s.get('run') == r['transcript_run'] and audio['sha256'] == r['audio_sha256']
                and audio['source'] == speech_media.identity(speech_media.source(path, load_project(path, path.name[4:])), path)
                and speech_media.local(path, audio['file']).is_file())


def view(path, locked=False, owned=False):
    s = state(path)
    if s['state'] == 'running' and not locked:
        s = task_timing.interrupted(s) | {'state': 'paused', 'message': '이전 작업이 중단됐습니다. 완료 결과는 유지되며 해당 작업을 다시 시작할 수 있습니다'}
    r = result(path)
    revision = edits(path, r['id'])['revision'] if r else 0
    from .speech_store import state as speech_state
    fresh_exports = (r and s.get('export_run') == r['id'] and s.get('export_revision') == revision
                     and s.get('export_speech_updated_at') == speech_state(path).get('updated_at'))
    return s | {'owned': owned, 'stale': bool(r and not current(path, r)), 'revision': revision,
                'exports': s.get('exports', {}) if fresh_exports else {}}


def overlaps(rows, turns):
    ordered=sorted(turns,key=lambda t:t['start_ms']); active=[];cursor=0
    for row in sorted(rows,key=lambda r:r['start_ms']):
        a, b = row['start_ms'], row['end_ms']
        active=[t for t in active if t['end_ms']>a]
        while cursor<len(ordered) and ordered[cursor]['start_ms']<b:
            active.append(ordered[cursor]);cursor+=1
        spans = defaultdict(list)
        for t in active:
            left, right = max(a, t['start_ms']), min(b, t['end_ms'])
            if left < right:
                spans[t['speaker']].append((left, right))
        weights = {}
        for speaker, intervals in spans.items():
            end, total = -1, 0
            for left, right in sorted(intervals):
                total += max(0, right - max(end, left)); end = max(end, right)
            weights[speaker] = total
        yield row, weights


def assign(rows, turns, prefix):
    labels = sorted({t['speaker'] for t in turns if t['speaker'] is not None}, key=lambda label: min(t['start_ms'] for t in turns if t['speaker'] == label))
    ids = {label: f'{prefix}-{i}' for i, label in enumerate(labels)}
    speakers = {ids[label]: f'{chr(65+i)}화자' if i < 26 else f'{i+1}번 화자' for i, label in enumerate(labels)}
    assignments = {}
    for row, weights in overlaps(rows, turns):
        a,b=row['start_ms'],row['end_ms']
        unknown=weights.pop(None,0)
        ranked = sorted(weights, key=weights.get, reverse=True)
        best = weights[ranked[0]] if ranked else 0
        # shortcut: 전사-발화 겹침에 근거한 보류이며 임베딩 신뢰도는 아니다. 방송 정답셋 확보 후 보정한다.
        reason = ('ambiguous' if unknown>=min(500,max(1,best*.2)) else 'no_voice' if not ranked else 'short' if best < 700 or best/(b-a) < .55 else
                  'mixed' if len(ranked) > 1 and weights[ranked[1]] >= min(500, best * .2) else None)
        assignments[row['id']] = {'speaker': ids[ranked[0]] if reason is None else None,
                                  'status': 'failed' if reason else 'automatic', 'reason': reason}
    return speakers, assignments


def failure_candidates(r, all_rows, edited_ids=()):
    """기존 자동 화자 ID의 단일 겹침 근거만 쓴다. 동일인 확률/새 음성 추론이 아니다."""
    turns=r.get('turns', []) if r else []
    labels=sorted({t['speaker'] for t in turns if t['speaker'] is not None}, key=lambda label:min(t['start_ms'] for t in turns if t['speaker']==label))
    ids=dict(zip(labels,r['speakers'])) if r else {}
    eligible=[row for row in all_rows if row['status']=='failed' and row['id'] not in edited_ids and row['reason'] not in ('mixed','manual','no_voice')]
    candidates={}
    for row, weights in overlaps(eligible,turns):
        # 200ms 미만의 스침·여러 화자·연결 실패 음성은 묶음 근거로 사용하지 않는다.
        if len(weights)==1:
            label, duration=next(iter(weights.items()))
            if label in ids and duration>=200:candidates[row['id']]=ids[label]
    return candidates


def matches(row, text):
    return text.casefold() in (row['text']+' '+row['speaker_name']+' '+REASONS.get(row['reason'], '')).casefold()


def decorate(path, transcript_run, rows):
    r = result(path)
    if not r or r['transcript_run'] != transcript_run or not current(path, r):
        return rows
    e = edits(path, r['id']); names = r['speakers'] | e['speakers'] | e['names']
    mapping = r['assignments'] | e['assignments']
    return [row | mapping.get(row['id'], {'speaker': None, 'status': 'failed', 'reason': 'no_voice'}) |
            {'speaker_name': names.get(mapping.get(row['id'], {}).get('speaker'), '화자인식 실패'),
             'speaker_reason': REASONS.get(mapping.get(row['id'], {}).get('reason'), ''), 'speaker_run': r['id']} for row in rows]


def rows(path):
    from . import speech_store
    r = result(path)
    if not r:
        return []
    if not current(path, r):
        return []
    run = speech_store.manifest(path)
    corrected = speech_store.corrections(path, run)
    return decorate(path, run['id'], [row | {'original_text': row['text'], 'text': corrected.get(row['id'], row['text'])}
                                     for row in speech_store.segments(path, run)])


def browse(path, query='', cursor=0, review=False, failed_query='', failed_cursor=0, failed_group=''):
    if type(review) is not bool:
        raise ValueError('화자 검토 조건이 올바르지 않습니다')
    for text, offset in ((query, cursor), (failed_query, failed_cursor)):
        if not isinstance(text, str) or len(text) > 200 or type(offset) is not int or offset < 0:
            raise ValueError('화자 검색 조건이 올바르지 않습니다')
    if not isinstance(failed_group,str) or len(failed_group)>200:
        raise ValueError('실패 후보 묶음 조건이 올바르지 않습니다')
    def page(items, offset):
        # 마지막 항목 배정 후 빈 마지막 페이지에 남지 않는다.
        offset = min(offset, max(0, (len(items)-1)//100)*100)
        return {'items':items[offset:offset+100], 'total':len(items), 'cursor':offset,
                'next_cursor':offset+100 if len(items)>offset+100 else None}
    r = result(path); all_rows = rows(path)
    items = [row for row in all_rows if (not review or row['status']!='failed') and matches(row, query)]
    e = edits(path, r['id']) if r else {}
    failed_review=None
    if review:
        candidates=failure_candidates(r,all_rows,e.get('assignments',{})); groups=defaultdict(list)
        for row in all_rows:
            if row['id'] in candidates:groups[candidates[row['id']]].append(row)
        names=(r['speakers'] | e['names']) if r else {}
        # 단독 후보는 개별 검토로 남긴다.
        groups={id:group for id,group in groups.items() if len(group)>1}
        active=failed_group if failed_group in groups or failed_group=='__ungrouped__' else ''
        failed_rows=[row for row in all_rows if row['status']=='failed' and matches(row,failed_query)
                     and (not active or (candidates.get(row['id']) not in groups if active=='__ungrouped__' else candidates.get(row['id'])==active))]
        samples=[]
        if active in groups and failed_rows:
            for row in (max(failed_rows,key=lambda row:row['end_ms']-row['start_ms']), failed_rows[0], failed_rows[-1]):
                if row not in samples:samples.append(row)
        failed_review=page(failed_rows,failed_cursor)|{'group':active,'query':failed_query,'samples':samples,
            'groups':[{'id':id,'name':names[id],'count':len(group)} for id,group in groups.items()]}
    speakers = []
    turns = r.get('turns', []) if r else []
    labels = sorted({t['speaker'] for t in turns if t['speaker'] is not None}, key=lambda label: min(t['start_ms'] for t in turns if t['speaker'] == label))
    turn_labels = dict(zip(r['speakers'], labels)) if r else {}
    for id, default in ((r['speakers'] | e['speakers']) if r else {}).items():
        selected = [row for row in all_rows if row['speaker'] == id]
        detected = [t for t in turns if t['speaker'] is not None and t['speaker'] == turn_labels.get(id)]
        speakers.append({'id': id, 'default': default, 'name': e['names'].get(id, default), 'count': len(selected),
                         'turn_count': len(detected), 'sample_kind': 'transcript' if selected else 'detected',
                         'sample': max(selected or detected, key=lambda row: row['end_ms']-row['start_ms'], default=None)})
    return {'run': r['id'] if r else None, 'backend_label':r.get('backend_label','sherpa-onnx · 기존') if r else None,
            'revision': e.get('revision', 0), 'speakers': speakers,
            **page(items, cursor), 'total_rows': len(all_rows), 'failed_review':failed_review,
            'failed': sum(row['status'] == 'failed' for row in all_rows), 'undo': bool(e.get('history')),
            'reasons': REASONS}


def edit(path, run, revision, action, **options):
    r = result(path)
    if not r or r['id'] != run or not current(path, r):
        raise Conflict('화자 분석 또는 입력이 바뀌었습니다. 현재 결과를 다시 확인하세요')
    e = edits(path, run)
    if type(revision) is not int or e['revision'] != revision:
        raise Conflict('다른 화면에서 수정됐습니다. 새 결과를 확인한 뒤 다시 저장하세요')
    before = {key: copy.deepcopy(e[key]) for key in ('names', 'assignments', 'speakers')}
    speakers = r['speakers'] | e['speakers']
    speaker = options.get('speaker')
    if action == 'rename':
        name = options.get('name')
        if speaker not in speakers or not isinstance(name, str) or len(name) > 80 or any(ord(c) < 32 for c in name):
            raise ValueError('화자와 이름을 확인하세요. 이름은 80자 이내입니다')
        if name.strip(): e['names'][speaker] = name.strip()
        else: e['names'].pop(speaker, None)
    elif action in ('assign', 'split', 'merge'):
        if action != 'split' and speaker is not None and speaker not in speakers:
            raise ValueError('대상 화자를 선택하세요')
        a, b = options.get('start_ms'), options.get('end_ms')
        if action == 'merge':
            source = options.get('source')
            if source not in speakers or speaker is None or source == speaker:
                raise ValueError('서로 다른 원래 화자와 대상 화자를 선택하세요')
            selected = [id for id, item in (r['assignments'] | e['assignments']).items() if item['speaker'] == source]
        elif 'candidate_speaker' in options:
            candidate=options['candidate_speaker'];query=options.get('query','')
            if not isinstance(candidate,str) or candidate not in r['speakers'] or not isinstance(query,str) or len(query)>200:
                raise ValueError('실패 후보 묶음과 검색 조건을 확인하세요')
            current_rows=rows(path);candidates=failure_candidates(r,current_rows,e['assignments'])
            selected=[row['id'] for row in current_rows if candidates.get(row['id'])==candidate and matches(row,query)]
            if not selected:raise Conflict('배정할 실패 후보가 없습니다. 목록을 다시 확인하세요')
        elif 'segment_id' in options:
            segment = options['segment_id']
            if not isinstance(segment, str) or not segment:
                raise ValueError('수정할 전사 발언을 선택하세요')
            # 듣고 고른 한 발언만 수정한다. 겹치는 이웃 발언까지 배정하지 않는다.
            selected = [row['id'] for row in rows(path) if row['id']==segment]
            if not selected: raise ValueError('선택한 전사 발언이 없습니다. 목록을 다시 확인하세요')
        else:
            if type(a) is not int or type(b) is not int or not 0 <= a < b <= r['duration_ms']:
                raise ValueError('수정할 시작·끝 시각을 확인하세요')
            selected = [row['id'] for row in rows(path) if row['start_ms'] < b and row['end_ms'] > a]
        if not selected:
            raise ValueError('선택 범위에 전사 발언이 없습니다')
        if action == 'split':
            speaker = run+'-'+uuid.uuid4().hex
            e['speakers'][speaker] = f'새 화자 {len(e["speakers"])+1}'
        reason = options.get('reason', 'manual') if speaker is None else None
        if speaker is None and reason not in REASONS:
            raise ValueError('화자인식 실패 이유를 선택하세요')
        for id in selected:
            e['assignments'][id] = {'speaker': speaker, 'status': 'confirmed' if speaker else 'failed', 'reason': reason}
    elif action == 'undo':
        if not e['history']:
            raise ValueError('되돌릴 변경이 없습니다')
        e.update(e['history'].pop())
    else:
        raise ValueError('화자 변경 종류가 올바르지 않습니다')
    if action != 'undo':
        e['history'] = (e['history'] + [before])[-50:]
    e['revision'] += 1
    save_json(local(path, f'runs/{run}/edits.json'), e)



def export(path):
    from .speech_store import timecode, state as speech_state
    r = result(path)
    if not r or not current(path, r):
        raise ValueError('현재 전사에 연결된 화자 분석이 필요합니다')
    items = rows(path); e = edits(path, r['id'])
    folder = f'exports/{uuid.uuid4().hex}'
    local(path, folder).mkdir(parents=True)
    save_json(local(path, folder+'/transcript.json'), {'speaker_run': r['id'], 'revision': e['revision'],
              'transcript_run': r['transcript_run'], 'time_base': '재생용 영상 시작=0ms', 'segments': items})
    safe = lambda s: "'"+s if s.startswith(('=', '+', '-', '@', '\t', '\r')) else s
    with local(path, folder+'/transcript.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f); w.writerow(['시작_ms','끝_ms','화자ID','화자이름','상태','실패이유','텍스트','원문'])
        for row in items:
            w.writerow([row['start_ms'], row['end_ms'], row['speaker'], safe(row['speaker_name']), row['status'],
                        REASONS.get(row['reason'], ''), safe(row['text']), safe(row['original_text'])])
    local(path, folder+'/transcript.txt').write_text('\n'.join(
        f"[{timecode(row['start_ms'])} → {timecode(row['end_ms'])}] {row['speaker_name']} ({row['status']} {REASONS.get(row['reason'], '')}): {row['text']}" for row in items), encoding='utf-8')
    update(path, exports={k: folder+'/transcript.'+k for k in ('json','csv','txt')}, export_revision=e['revision'], export_run=r['id'],
           export_speech_updated_at=speech_state(path).get('updated_at'))
