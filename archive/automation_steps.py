"""기존 작업 API를 순서대로 호출한다. 말소리 분리 단계는 만들지 않는다."""
import shutil
import threading

from . import speech_store, speech_media, speech_model, context_model, context_job, context_full, voice_store
from . import diarization_backends, analysis_store
from .storage import project_path, load_project, read_json


class Prerequisite(ValueError):
    pass


class Paused(Exception):
    pass


def wait(queue, job):
    if not job:
        return
    while not job.closed:
        if queue.stop.is_set():
            job.cancel('all') if hasattr(job, 'workers') else job.cancel()
        threading.Event().wait(.2)
    observer = getattr(job, 'report_thread', None)
    if observer:
        observer.join()
    if queue.stop.is_set():
        raise Paused()


def ready(module):
    status = module.status()
    if not status.get('ready') or not status.get('engine'):
        raise Prerequisite('전사·Gemma 모델과 실행 도구를 각 메뉴에서 준비한 뒤 대기열을 이어가세요')


def execute(queue, entry, stage):
    manager, root, vod, settings = queue.manager, queue.root, entry['vod'], entry['options']
    path = project_path(root, vod)
    if shutil.disk_usage(path).free < 256 * 1024**2:
        raise Prerequisite('저장 공간이 부족합니다. 공간 확보 후 이어가세요')
    if stage == 'download':
        # 이미 받은 자료는 다운로드기의 기존 검증·이어받기 규칙을 따른다.
        before = load_project(path, vod)
        reused = all(t['state'] in ('complete', 'empty', 'unavailable') for t in before['tasks'].values())
        manager.start(root, vod, entry['format'], 'all')
        if reused:
            manager.reports.skipped(path, stage)
        wait(queue, manager.job if manager.job and manager.job.project.path == path else None)
        data = load_project(path, vod)
        if data['tasks']['video']['state'] != 'complete':
            raise ValueError('영상 다운로드·검증을 완료하지 못했습니다. 가져오기 진행에서 상세 오류를 확인하세요')
        chat = data['tasks']['chat']
        if chat['state'] not in ('complete', 'empty', 'unavailable'):
            if settings['allow_partial_chat'] and chat['state'] == 'review' and chat.get('assets', {}).get('jsonl'):
                return 'partial'
            raise ValueError('채팅 제공 범위 검증이 끝나지 않았습니다. 해당 VOD를 확인한 뒤 재시도하세요')
        return 'complete'
    data = load_project(path, vod)
    if stage == 'audio':
        raw = speech_store.state(path).get('raw_audio')
        if raw and raw.get('source') == speech_media.identity(speech_media.source(path, data), path) and speech_media.local(path, raw['file']).is_file():
            speech_media.validate_wav(speech_media.local(path, raw['file']), raw['duration_ms'], queue.stop)
            manager.reports.skipped(path, stage)
            return 'reused'
        info = manager.speech_info(root, vod)
        if not info['tracks']:
            raise ValueError('오디오 트랙이 없습니다')
        if len(info['tracks']) != 1:
            raise ValueError('오디오 트랙이 여러 개입니다. 음성 전사 메뉴에서 사용할 트랙을 추출한 뒤 재시도하세요')
        manager.speech_start(root, vod, 'audio', track=info['tracks'][0]['index'])
        wait(queue, manager.speech_job)
        status = speech_store.state(path)
    elif stage == 'transcribe':
        current = speech_store.view(path, data)
        run = speech_store.manifest(path)
        if run and run['complete'] and not current['stale'] and speech_store.input_info(run)['input_kind'] == 'original' and run['language'] == settings['language'] and speech_store.input_info(run)['asr_options'] == settings['asr_options']:
            speech_store.segments(path, run)
            manager.reports.skipped(path, stage)
            return 'reused'
        ready(speech_model)
        manager.speech_start(root, vod, 'transcribe', language=settings['language'], asr_options=settings['asr_options'])
        wait(queue, manager.speech_job)
        status = speech_store.state(path)
    elif stage == 'diarize':
        result = voice_store.result(path)
        if result and voice_store.current(path, result):
            # 수동 배정이 포함된 현재 화자 결과는 자동화가 교체하지 않는다.
            manager.reports.skipped(path, stage)
            return 'reused'
        status = diarization_backends.status(settings['backend'])
        if not status['supported'] or not status['ready'] or not status['engine']:
            raise Prerequisite('선택한 화자 모델·도구를 먼저 준비하세요. 이용 동의는 자동으로 진행하지 않습니다')
        manager.voices_start(root, vod, 'diarize', {'backend': settings['backend'], 'speakers': -1})
        wait(queue, manager.voice_job)
        status = voice_store.state(path)
    elif stage == 'reactions':
        if not data['tasks']['chat'].get('assets', {}).get('jsonl') and data['tasks']['chat']['state'] in ('empty', 'unavailable'):
            manager.reports.skipped(path, stage, skipped=True)
            return 'skipped'
        old = analysis_store.load(path, data)
        if old and not old['stale']:
            manager.reports.skipped(path, stage)
            return 'reused'
        manager.analyze(root, vod, {}, settings['allow_partial_chat'])
        return 'complete'
    elif stage == 'summary':
        state = context_job.state(path)
        run = state.get('full_run')
        action = 'whole'
        if run:
            saved = read_json(context_job.local(path, f'runs/{run}/result.json'))
            matching = saved.get('version') == context_full.VERSION and saved.get('model') == context_model.DEFAULT_NAME and saved.get('fingerprint') == context_full.fingerprint(context_full.current_source(path, vod, saved.get('chat_offset_ms', 0)))
            thinking = (saved.get('inference') or {}).get('thinking', True)
            if matching and thinking == settings['thinking']:
                if saved.get('complete'):
                    manager.reports.skipped(path, stage)
                    return 'reused'
                action = 'resume'
        ready(context_model)
        manager.context_start(root, vod, action, {'thinking': settings['thinking']})
        wait(queue, manager.context_job)
        status = context_job.state(path)
    else:
        raise ValueError('지원하지 않는 자동화 단계입니다')
    if status['state'] == 'review' and stage == 'summary':
        return 'partial'
    if status['state'] != 'complete':
        raise ValueError(status.get('message') or '작업을 완료하지 못했습니다')
    return 'complete'
