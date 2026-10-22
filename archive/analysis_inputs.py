"""저장된 전사·화자 입력의 설명과 명시적 선택. 현재 열어 둔 버전을 바꾸지 않는다."""
from functools import lru_cache
import re

from . import speech_store, speech_media, voice_store
from .storage import read_json

LANGUAGES = {'ko': '한국어', 'en': '영어', 'ja': '일본어', 'auto': '언어 자동'}
VAD = {'standard': '발화 검출 표준', 'sensitive': '발화 검출 민감', 'off': '발화 검출 끄기'}


def run_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{32}', value):
        raise ValueError('저장된 데이터 목록에서 선택하세요')
    return value


def transcript_label(run):
    info = speech_store.input_info(run)
    settings = info['asr_options']
    return ' · '.join([
        run.get('created_at', '생성일 미기록'), run.get('model', 'Whisper · 이전 기록'),
        LANGUAGES.get(run.get('language'), '언어 미기록'), info['input_label'],
        VAD.get(settings.get('vad'), '이전 발화 검출'),
        '용어 힌트 있음' if settings.get('prompt') else '용어 힌트 없음',
        '완료' if run.get('complete') else '일부 처리',
        f"{run.get('segment_count', 0)}개 발언", str(run['id'])[:8]])


def transcripts(path):
    deleted = speech_store.state(path).get('deleted_runs', [])
    result = []
    for file in speech_media.local(path, 'runs').glob('*/manifest.json'):
        if file.is_symlink() or file.parent.is_symlink() or file.parent.name in deleted:
            continue
        try:
            run = read_json(file)
            if run_id(run['id']) != file.parent.name:
                continue
            result.append({key: run.get(key) for key in
                           ('id', 'created_at', 'complete', 'segment_count', 'duration_ms', 'language', 'model')}
                          | speech_store.input_info(run)
                          | {'label': transcript_label(run), 'quality_revision': run.get('quality_revision', 0)})
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return sorted(result, key=lambda r: (r.get('created_at') or '', r['id']), reverse=True)


@lru_cache(maxsize=128)
def _voice_info(file, modified, size):
    # 긴 방송의 배정 전체를 화면 폴링 때마다 다시 읽지 않고 작은 설명만 캐시한다.
    r = read_json(file)
    return {key: r.get(key) for key in ('id', 'created_at', 'transcript_run', 'duration_ms')} | {
        'backend_label': r.get('backend_label', 'sherpa-onnx · 이전 기록'),
        'speaker_count': len(r.get('speakers', {})), 'segment_count': len(r.get('assignments', {}))}


def speakers(path):
    result = []
    for id in voice_store.state(path).get('runs', []):
        try:
            run_id(id)
            file = voice_store.local(path, f'runs/{id}/result.json')
            stat = file.stat()
            item = dict(_voice_info(file, stat.st_mtime_ns, stat.st_size))
            if item['id'] != id:
                continue
            item['label'] = ' · '.join([
                item.get('created_at') or '생성일 미기록', item['backend_label'],
                f"{item['speaker_count']}개 화자 · {item['segment_count']}개 발언",
                f"전사 {str(item['transcript_run'])[:8]}", id[:8]])
            result.append(item)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return sorted(result, key=lambda r: (r.get('created_at') or '', r['id']), reverse=True)


def catalog(path):
    return {'transcripts': transcripts(path), 'speakers': speakers(path),
            'transcript_run': speech_store.state(path).get('run'),
            'speaker_run': voice_store.state(path).get('run')}


def selected(path, data, selection):
    if not isinstance(selection, dict) or set(selection) != {'transcript_run', 'speaker_run'}:
        raise ValueError('전사 데이터와 화자 정보 사용 여부를 선택하세요')
    id = run_id(selection['transcript_run'])
    if id not in {r['id'] for r in transcripts(path)}:
        raise ValueError('선택한 전사 데이터가 삭제되었거나 읽을 수 없습니다')
    run = speech_store.manifest(path, {'run': id})
    if not run.get('complete'):
        raise ValueError('전체 처리가 완료된 전사 데이터를 선택하세요')
    audio = speech_store.audio_for_run(path, run)
    if not audio or audio.get('source') != speech_media.identity(speech_media.source(path, data), path):
        raise ValueError('선택한 전사는 현재 영상과 다른 입력입니다')
    edits = speech_store.corrections(path, run)
    rows = [r | {'text': edits.get(r['id'], r['text']), 'corrected': r['id'] in edits}
            for r in speech_store.segments(path, run)]
    speaker_id = selection['speaker_run']
    label = transcript_label(run)
    notes = ['전사 전체 범위 처리 · 정확도 확인 필요']
    if speaker_id is not None:
        run_id(speaker_id)
        voice = voice_store.result(path, speaker_id)
        if not voice or voice['transcript_run'] != id or voice['audio_sha256'] != audio['sha256']:
            raise ValueError('선택한 화자 데이터는 이 전사와 연결된 분석이 아닙니다')
        rows = voice_store.decorate_result(path, voice, rows)
        label += ' / ' + next(r['label'] for r in speakers(path) if r['id'] == speaker_id)
    else:
        notes.append('화자 정보 사용 안 함')
    return {'speech': rows, 'notes': notes, 'selection': dict(selection), 'label': label}
