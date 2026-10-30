"""기존 작업 API를 순서대로 호출한다. 말소리 분리 단계는 만들지 않는다."""
import shutil
import threading

from . import speech_store, speech_media, speech_model, context_model, context_job, voice_store
from . import diarization_backends, analysis_store, automation_media, automation_summary, automation_plan, download_scope
from .storage import project_path, load_project
from .source import Cancelled


class Prerequisite(ValueError):
    pass


class Paused(Exception):
    pass


class MissingInput(ValueError):
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


def check_inputs(path, data, settings, stage):
    """미선택 단계의 자료만 확인한다. 다운로드·추출·전사를 대신 시작하지 않는다."""
    chosen = automation_plan.selected(settings)
    if stage == 'audio' and 'download' not in chosen:
        try:
            speech_media.source(path, data)
        except (ValueError, OSError, KeyError) as error:
            raise MissingInput('완료된 영상이 필요합니다. 영상·채팅 다운로드를 선택해 다시 등록하거나 먼저 다운로드를 완료하세요') from error
    if stage == 'transcribe' and 'audio' not in chosen:
        raw = speech_store.state(path).get('raw_audio') or speech_store.state(path).get('audio')
        try:
            valid = (raw and not raw.get('separation_run') and raw.get('input_kind', 'original') == 'original'
                     and raw['source'] == speech_media.identity(speech_media.source(path, data), path)
                     and speech_media.local(path, raw['file']).is_file())
        except (ValueError, OSError, KeyError):
            valid = False
        if not valid:
            raise MissingInput('현재 영상의 원음 오디오가 필요합니다. 원음 오디오 추출을 선택해 다시 등록하거나 먼저 추출하세요')
    if stage in ('diarize', 'reactions', *automation_summary.STAGES.values()) and 'transcribe' not in chosen:
        try:
            run = speech_store.manifest(path)
            valid = run and run['complete'] and not speech_store.view(path, data)['stale']
        except (ValueError, OSError, KeyError):
            valid = False
        if not valid:
            raise MissingInput('현재 영상의 완료된 전사가 필요합니다. 전사 진행을 선택해 다시 등록하거나 먼저 전사를 완료하세요')


def execute(queue, entry, stage):
    manager, root, vod, settings = queue.manager, download_scope.entry_root(queue.root,entry), entry['vod'], entry['options']
    path = project_path(root, vod)
    if shutil.disk_usage(path).free < 256 * 1024**2:
        raise Prerequisite('저장 공간이 부족합니다. 공간 확보 후 이어가세요')
    if stage == 'download':
        try:
            prepared = automation_media.prepare(path, vod, settings['allow_partial_chat'], queue.stop)
        except Cancelled as error:
            raise Paused() from error
        needed = [kind for kind, valid in prepared.items() if not valid]
        if needed:
            manager.start(root, vod, entry['format'], 'all' if len(needed) == 2 else needed[0])
            wait(queue, manager.job if manager.job and manager.job.project.path == path else None)
        else:
            manager.reports.skipped(path, stage)
        data = load_project(path, vod)
        if data['tasks']['video']['state'] != 'complete':
            raise ValueError('영상 다운로드·검증을 완료하지 못했습니다. 가져오기 진행에서 상세 오류를 확인하세요')
        chat = data['tasks']['chat']
        if chat['state'] not in ('complete', 'empty', 'unavailable'):
            if settings['allow_partial_chat'] and chat['state'] == 'review' and chat.get('assets', {}).get('jsonl'):
                return 'partial'
            raise ValueError('채팅 제공 범위 검증이 끝나지 않았습니다. 해당 VOD를 확인한 뒤 재시도하세요')
        return 'complete' if needed else 'reused'
    data = load_project(path, vod)
    check_inputs(path, data, settings, stage)
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
        if not data['tasks']['chat'].get('assets', {}).get('jsonl'):
            manager.reports.skipped(path, stage, skipped=True)
            return 'skipped'
        old = analysis_store.load(path, data)
        if old and not old['stale']:
            manager.reports.skipped(path, stage)
            return 'reused'
        manager.analyze(root, vod, {}, settings['allow_partial_chat'])
        return 'complete'
    elif stage in automation_summary.STAGES.values():
        action, values = automation_summary.request(path, vod, stage, settings)
        if action is None:
            report_stage, report_settings = automation_summary.report(stage)
            manager.reports.skipped(path, report_stage, settings=report_settings)
            return 'reused'
        ready(context_model)
        manager.context_start(root, vod, action, values)
        wait(queue, manager.context_job)
        status = context_job.state(path)
    else:
        raise ValueError('지원하지 않는 자동화 단계입니다')
    if status['state'] == 'review' and stage in automation_summary.STAGES.values():
        return 'partial'
    if status['state'] != 'complete':
        raise ValueError(status.get('message') or '작업을 완료하지 못했습니다')
    return 'complete'
