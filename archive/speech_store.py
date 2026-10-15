"""음성 상태, 전사 조각·교정·내보내기의 분리 보존."""

import csv
from collections import Counter
import json
import math
import uuid

from .speech_media import local, identity, source
from .storage import read_json, save_json, stamp
from . import task_timing, sam_options, roformer_models

CHUNK_MS = 300000


def state(path):
    file = local(path, 'state.json')
    return read_json(file) if file.exists() else {'state': 'idle', 'message': '음성 추출부터 시작하세요', 'progress': {}}


def update(path, **values):
    value = task_timing.update(state(path), values) | {'updated_at': stamp()}
    save_json(local(path, 'state.json'), value)
    return value


def manifest(path, value=None):
    run = (value or state(path)).get('run')
    return read_json(local(path, f'runs/{run}/manifest.json')) if run else None


def input_info(run):
    """이전 버전은 실행 당시 입력 기록에서 복원하며 파일을 다시 쓰지 않는다."""
    audio = run.get('input_audio') or {}
    kind = run.get('input_kind', audio.get('input_kind', 'sam' if audio.get('separation_run') else 'original'))
    profile = audio.get('sam_profile', 'standard') if kind == 'sam' else None
    label = 'SAM 분리음 · '+sam_options.label(profile) if kind == 'sam' else '원본 오디오'
    if kind == 'roformer': label = roformer_models.NAME+' · '+roformer_models.profile(audio.get('separation_profile','fast'))['label']
    return {'input_kind': kind, 'sam_profile': profile,
            'separation_run': run.get('separation_run', audio.get('separation_run')),
            'input_label': label, 'asr_options': run.get('asr_options', {'vad':'standard','prompt':''})}


def matching_run(path, signature):
    """설정을 바꿨다가 돌아와도 동일 입력의 완료·중단 결과를 찾아 재사용한다."""
    value = state(path)
    ids = [value.get('pending_run'), value.get('run')]
    files = sorted(local(path, 'runs').glob('*/manifest.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    ids += [file.parent.name for file in files if not file.is_symlink() and not file.parent.is_symlink()]
    for run_id in dict.fromkeys(ids):
        if not run_id: continue
        try:
            run = manifest(path, {'run': run_id})
            compared = run | input_info(run)
            compared.setdefault('source_audio_sha256', run.get('audio_sha256'))
            if all(compared.get(key) == val for key, val in signature.items()): return run
        except (OSError, ValueError, KeyError, TypeError):
            continue  # 손상된 다른 실행은 보존하고 현재 입력은 별도 실행으로 처리한다.
    return None


def view(path, data, busy=False, owned=False):
    value = state(path)
    if value['state'] in ('running', 'stopping') and not busy:
        value = task_timing.interrupted(value) | {'state': 'paused', 'message': '이전 음성 작업이 중단됐습니다. 완료 조각에서 이어받을 수 있습니다'}
    audio = value.get('audio')
    stale = False
    if audio:
        try:
            stale = audio['source'] != identity(source(path, data), path) or not local(path, audio['file']).is_file()
        except (ValueError, OSError):
            stale = True
    run = manifest(path, value)
    if run:
        value['transcript'] = {key: run[key] for key in ('id', 'language', 'duration_ms', 'processed_ms', 'complete', 'segment_count', 'chunks', 'audio_sha256')}
        value['transcript'].update(input_info(run))
        value['transcript']['quality_revision'] = run.get('quality_revision',0)
        stale |= not audio or run.get('source_audio_sha256', run['audio_sha256']) != audio['sha256']
    versions = []
    folder = local(path, 'runs')
    if folder.exists():
        for file in sorted(folder.glob('*/manifest.json')):
            if file.is_symlink() or file.parent.is_symlink(): continue
            try:
                saved = read_json(file)
                versions.append({k: saved[k] for k in ('id', 'created_at', 'complete', 'segment_count')} | input_info(saved) | {'quality_revision':saved.get('quality_revision',0)})
            except (OSError, ValueError, KeyError, TypeError):
                value['version_warning'] = '일부 이전 전사 기록을 읽지 못했습니다. 해당 파일은 보존했습니다'
    value['versions'] = sorted(versions, key=lambda v: v['created_at'], reverse=True)
    return value | {'stale': stale, 'owned': owned}


def read_engine_output(file):
    if file.is_symlink():
        raise ValueError('전사 엔진 출력의 연결 파일은 사용할 수 없습니다')
    try:
        # 엔진이 발언 안에 불완전한 UTF-8 바이트를 출력할 수 있다. 원출력은 변경하지 않는다.
        raw = json.loads(file.read_text(encoding='utf-8', errors='surrogateescape'))
        if not isinstance(raw, dict) or not isinstance(raw.get('transcription'), list):
            raise ValueError()
        for item in raw['transcription']:
            if not isinstance(item, dict):
                raise ValueError()
            text = item.get('text')
            if isinstance(text, str) and any('\ud800' <= c <= '\udfff' or c == '\ufffd' for c in text):
                item.update(text='[문자 인식 오류 · 원음 확인 필요]', encoding_review=True)
        json.dumps(raw, ensure_ascii=False).encode('utf-8')
    except ValueError:
        raise ValueError('전사 엔진 출력 형식 또는 메타데이터가 손상됐습니다. 원출력을 보존했으며 현재 조각을 재시도할 수 있습니다') from None
    return raw


def normalize(raw, start, end, index):
    items = raw.get('transcription')
    if not isinstance(items, list):
        raise ValueError('전사 엔진 출력 형식이 올바르지 않습니다')
    result, previous = [], start
    for number, item in enumerate(items):
        offsets = item.get('offsets', {})
        a, b, text = offsets.get('from'), offsets.get('to'), item.get('text')
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (a, b)) or not isinstance(text, str):
            raise ValueError('전사 시각 또는 텍스트 형식이 올바르지 않습니다')
        # Whisper의 마지막 30초 창 패딩이 실제 오디오 끝보다 길 수 있다.
        if a < 0 or b < a or a >= end - start or b > end - start + 30000:
            raise ValueError('전사 시각이 오디오 조각 범위를 벗어났습니다')
        adjusted = b > end - start
        a, b = max(start, round(start + a)), min(end, round(start + b))
        if a < previous:
            raise ValueError('전사 구간의 순서가 겹칩니다. 엔진 원출력을 확인하세요')
        if not text.strip() or b <= a:
            continue
        result.append({'id': f'{index:05d}-{number:05d}', 'start_ms': a, 'end_ms': b,
                       'text': text.strip(), 'timing_adjusted': adjusted,
                       'encoding_review': bool(item.get('encoding_review')),
                       'boundary_review': (index > 0 and a < start + 2000) or b > end - 2000})
        previous = b
    return result


def segments(path, run):
    result, end = [], 0
    for chunk in run['chunks']:
        if chunk['start_ms'] != end or chunk['end_ms'] <= end or chunk['end_ms'] > run['duration_ms']:
            raise ValueError('전사 처리 범위의 누락 또는 중복이 있습니다')
        saved = read_json(local(path, f"runs/{run['id']}/{chunk['file']}"))
        if saved['start_ms'] != end or saved['end_ms'] != chunk['end_ms']:
            raise ValueError('전사 체크포인트 범위가 일치하지 않습니다')
        counts = Counter(row['text'] for row in saved['segments'])
        for row in saved['segments']:
            if type(row.get('start_ms')) is not int or type(row.get('end_ms')) is not int or not end <= row['start_ms'] < row['end_ms'] <= chunk['end_ms']:
                raise ValueError('저장된 전사 시각이 조각 범위와 일치하지 않습니다')
            result.append(row if run.get('quality_revision') else row | {'repeat_review': len(row['text']) >= 4 and counts[row['text']] >= 3})
        end = chunk['end_ms']
    if end != run['processed_ms'] or (run['complete'] and end != run['duration_ms']):
        raise ValueError('전사 완료 범위를 확인할 수 없습니다')
    return result


def corrections(path, run):
    file = local(path, f"runs/{run['id']}/corrections.json")
    return read_json(file) if file.exists() else {}


def result(path, query='', cursor=0):
    if not isinstance(query, str) or len(query) > 200 or type(cursor) is not int or cursor < 0:
        raise ValueError('전사 검색 조건이 올바르지 않습니다')
    run = manifest(path)
    if not run:
        return {'items': [], 'next_cursor': None, 'total': 0, 'run': None}
    edits = corrections(path, run)
    rows = [row | {'original_text': row['text'], 'text': edits.get(row['id'], row['text']), 'corrected': row['id'] in edits}
            for row in segments(path, run)]
    from .voice_store import decorate
    try:
        rows = decorate(path, run['id'], rows)
    except (ValueError, KeyError, OSError, TypeError):
        pass  # M4 상태 손상이 원 전사 열기를 막지 않도록 한다.
    rows = [row for row in rows if query.casefold() in (row['text']+' '+row.get('speaker_name', '')).casefold()]
    return {'items': rows[cursor:cursor + 100], 'next_cursor': cursor + 100 if len(rows) > cursor + 100 else None,
            'total': len(rows), 'run': run['id'], 'complete': run['complete'], 'processed_ms': run['processed_ms']}


def correct(path, run_id, segment_id, text):
    run = manifest(path)
    if not run or run['id'] != run_id:
        raise ValueError('전사 실행이 바뀌었습니다. 목록을 다시 확인하세요')
    rows = {row['id']: row for row in segments(path, run)}
    if segment_id not in rows or (text is not None and (not isinstance(text, str) or len(text) > 5000)):
        raise ValueError('교정할 전사 행과 텍스트를 확인하세요')
    edits = corrections(path, run)
    if text is None or text == rows[segment_id]['text']:
        edits.pop(segment_id, None)
    else:
        edits[segment_id] = text
    save_json(local(path, f"runs/{run_id}/corrections.json"), edits)


def timecode(ms):
    seconds = ms // 1000
    return f'{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}.{ms % 1000:03}'


def export(path):
    run = manifest(path)
    if not run:
        raise ValueError('먼저 전사할 자료가 필요합니다')
    edits = corrections(path, run)
    rows = [row | {'original_text': row['text'], 'text': edits.get(row['id'], row['text']), 'corrected': row['id'] in edits}
            for row in segments(path, run)]
    relative = f"exports/{uuid.uuid4().hex}"
    folder = local(path, relative)
    folder.mkdir(parents=True)
    label = '전체 범위 처리 · 정확도 확인 필요' if run['complete'] else '일부 범위 처리'
    save_json(folder / 'transcript.json', {'status': label, 'run': run, 'segments': rows})
    with (folder / 'transcript.csv').open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['상태', '구간ID', '시작_ms', '끝_ms', '시작', '끝', '교정문', '원문', '교정됨', '경계검토', '문자인식오류'])
        for row in rows:
            # 스프레드시트에서 전사 본문을 수식으로 실행하지 않도록 한다.
            safe = lambda s: "'" + s if s.startswith(('=', '+', '-', '@', '\t', '\r')) else s
            writer.writerow([label, row['id'], row['start_ms'], row['end_ms'], timecode(row['start_ms']),
                             timecode(row['end_ms']), safe(row['text']), safe(row['original_text']), row['corrected'], row['boundary_review'], row.get('encoding_review', False)])
    (folder / 'transcript.txt').write_text(label + '\n' + '\n'.join(
        f"[{timecode(row['start_ms'])} → {timecode(row['end_ms'])}] {row['text']}" for row in rows), encoding='utf-8')
    files = {key: f'{relative}/transcript.{key}' for key in ('json', 'csv', 'txt')}
    update(path, exports=files)
    return files


def select(path, run_id):
    if not isinstance(run_id, str) or len(run_id) != 32 or any(c not in '0123456789abcdef' for c in run_id):
        raise ValueError('저장된 전사 버전을 선택하세요')
    run = manifest(path, {'run': run_id}); segments(path, run)
    audio = run.get('source_audio')
    if not audio:
        wanted = run.get('source_audio_sha256', run['audio_sha256'])
        for file in local(path, 'audio-history').glob('*.json'):
            candidate = read_json(file)
            if candidate.get('sha256') == wanted: audio = candidate; break
        if not audio:
            candidate = state(path).get('audio')
            if candidate and candidate['sha256'] == wanted: audio = candidate
    if not audio: raise ValueError('이전 전사의 원음 정보를 찾을 수 없습니다. 파일은 보존되어 있습니다')
    update(path, run=run_id, audio=audio, exports={})
