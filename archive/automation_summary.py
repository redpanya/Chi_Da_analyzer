"""자동 요약의 모드별 입력·재사용·이어하기 결정. 기존 결과에는 쓰지 않는다."""
from . import context_job, context_full, context_timestamps, context_clips_local
from . import context_exchange_data, context_clip_model, context_model, context_server
from . import context_background, context_guidance, speech_store, voice_store
from .storage import read_json

MODES = ('timestamps', 'detail', 'clips')
STAGES = {'detail': 'summary', 'timestamps': 'timestamps', 'clips': 'clips'}


def validate(value, analysis=True):
    if (not isinstance(value, list) or len(value) > 3
            or any(not isinstance(mode, str) or mode not in MODES for mode in value)
            or len(set(value)) != len(value) or (analysis and not value)):
        raise ValueError('AI 요약 모드를 하나 이상 선택하세요. 중복되거나 알 수 없는 모드는 사용할 수 없습니다')
    return [mode for mode in MODES if mode in value]


def report(stage):
    return ('summary', {'summary_mode': 'detail' if stage == 'summary' else stage}) if stage in STAGES.values() else (stage, None)


def request(path, vod, stage, settings):
    mode = 'detail' if stage == 'summary' else stage
    selection = {'transcript_run': speech_store.state(path).get('run'), 'speaker_run': None}
    voice = voice_store.result(path) if settings['speakers_enabled'] else None
    if voice and voice_store.current(path, voice):
        selection['speaker_run'] = voice['id']
    wanted = {'thinking': settings['thinking'], 'selection': selection}
    guidance=context_guidance.prepare(path,mode,settings)
    wanted.update(background=guidance['background'],custom_request=guidance['custom_request'])
    if mode == 'clips':
        wanted['include_chat'] = True
    action, resume, scope, prepare = {
        'detail': ('whole', 'resume', 'full', context_full.prepare),
        'timestamps': ('timestamps', 'timestamps-resume', 'timestamps', context_timestamps.prepare),
        'clips': ('clips', 'clips-resume', 'clips-local', context_clips_local.prepare),
    }[mode]
    fingerprints = {}
    pending = None
    for entry in reversed(context_job.state(path).get('runs', [])):
        if entry.get('scope') != scope:
            continue
        try:
            saved = read_json(context_job.local(path, f"runs/{entry['id']}/result.json"))
            if saved.get('analysis_guidance') != guidance:continue
            if saved.get('inference') != context_server.profile(settings['thinking']):
                continue
            if 'input_selection' in saved and saved['input_selection'] != selection:
                continue
            if mode == 'detail':
                from .context_adaptive import REVISION
                if (saved.get('version') != context_full.VERSION or saved.get('pipeline_revision') != REVISION
                        or saved.get('model') != context_model.DEFAULT_NAME
                        or saved.get('model_sha256') != context_model.spec()['sha256']):
                    continue
                # 입력 선택이 없던 이전 상세 결과도 당시 기본 입력과 일치할 때만 재사용한다.
                legacy = 'input_selection' not in saved
                if legacy and not settings['speakers_enabled'] and voice_store.result(path):
                    continue
                if legacy not in fingerprints:
                    source = context_full.current_source(path, vod, 0, wanted['background'], None if legacy else selection,guidance)
                    fingerprints[legacy] = context_full.fingerprint(source)
                digest = fingerprints[legacy]
            else:
                if saved.get('origin') != 'local' or saved.get('revision') != context_exchange_data.REVISION:
                    continue
                if mode == 'clips' and saved.get('policy_revision') != context_clip_model.REVISION:
                    continue
                if mode not in fingerprints:
                    source = context_exchange_data.snapshot(path, vod, selection, include_chat=mode == 'clips')
                    if mode=='clips':
                        from .context_clip_chat import attach
                        source=attach(source)
                    fingerprints[mode] = context_exchange_data.fingerprint(context_guidance.attach(source,guidance))
                digest = fingerprints[mode]
            if saved.get('fingerprint') != digest:
                continue
            if saved.get('complete'):
                return None, wanted
            if pending is None:
                # 기존 prepare의 체크포인트·버전·입력 검증도 통과해야 이어받는다.
                prepare(path, vod, resume, {'run': entry['id']})
                pending = (resume, {'run': entry['id']})
        except (ValueError, KeyError, TypeError, FileNotFoundError):
            # 손상·삭제·정책 변경 결과는 보존하고 다른 일치 결과를 찾는다.
            continue
    return pending or (action, wanted)
