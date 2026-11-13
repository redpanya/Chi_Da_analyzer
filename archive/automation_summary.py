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


def _external_complete(path, vod, entry, saved, mode, selection, guidance):
    from . import context_exchange as exchange, context_clip_chat
    if (saved.get('id') != entry['id'] or saved.get('scope') != 'external' or saved.get('origin') != 'external'
            or saved.get('mode') != mode or entry.get('mode') != mode or saved.get('complete') is not True
            or saved.get('revision') != context_exchange_data.REVISION or saved.get('input_selection') != selection
            or saved.get('analysis_guidance') != guidance or saved.get('include_chat') is not (mode != 'timestamps')
            or saved.get('chat_offset_ms') != 0):
        return False
    if mode == 'clips' and saved.get('clip_chat_revision') != context_clip_chat.REVISION:
        return False
    if context_exchange_data.stale(path, vod, saved):
        return False
    source = read_json(context_job.local(path, f"runs/{entry['id']}/source.json"))
    work = read_json(context_job.local(path, f"runs/{entry['id']}/work.json"))
    if not isinstance(source, dict) or not isinstance(work, dict):
        return False
    chunks, replies = work['chunks'], work['replies']
    if (not isinstance(chunks, list) or not isinstance(replies, dict)
            or context_exchange_data.fingerprint(source) != saved['fingerprint'] or not chunks
            or len({c['id'] for c in chunks}) != len(chunks) or set(replies) != {c['id'] for c in chunks}):
        return False
    cursor = chat_cursor = 0
    packet = saved | {'id': saved['export_id'], 'chunks': chunks}
    exchange.folder(path, saved['export_id'])
    chat_index = context_clip_chat.Index(source) if mode == 'clips' else None
    for chunk in chunks:
        first, last = chunk['first'], chunk['last']
        if (chunk.get('error') or type(first) is not int or type(last) is not int or first != cursor
                or not first < last <= len(source['rows']) or chunk['chat_first'] != chat_cursor
                or not chat_cursor <= chunk['chat_last'] <= len(source['chat'])):
            return False
        raw = replies[chunk['id']]
        rows = source['rows'][first:last]
        envelope = dict(schema_version=1, export_id=saved['export_id'], chunk_id=chunk['id'], mode=mode,
                        coverage={'first_id': rows[0]['id'], 'last_id': rows[-1]['id']}) | raw
        exchange.validate_entry(packet, source, envelope, chat_index)
        if any(item['review_needed'] for item in raw['clips' if mode == 'clips' else 'topics']):
            return False
        cursor, chat_cursor = last, chunk['chat_last']
    return cursor == len(source['rows']) and chat_cursor == len(source['chat'])


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
        if entry.get('scope') not in (scope, 'external'):
            continue
        try:
            saved = read_json(context_job.local(path, f"runs/{entry['id']}/result.json"))
            if not isinstance(saved, dict):
                continue
            if entry.get('scope') == 'external':
                if _external_complete(path, vod, entry, saved, mode, selection, guidance):
                    return None, wanted
                continue
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
        except (OSError, ValueError, KeyError, TypeError, IndexError):
            # 손상·삭제·정책 변경 결과는 보존하고 다른 일치 결과를 찾는다.
            continue
    return pending or (action, wanted)
