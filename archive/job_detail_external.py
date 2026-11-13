"""외부 AI 패키지의 수신 상태를 로컬 추론 상태와 분리해 읽는다."""
from . import context_exchange_data
from .job_detail import MODES, _field, _id, _json
from .storage import Conflict, load_project, project_path


def detail(manager, request, out):
    export_id = _id(request.get('id'))
    if request.get('export_id', export_id) != export_id:
        raise Conflict('선택한 외부 작업 번호가 일치하지 않습니다')
    path = project_path(request['root'], request['vod_id'])
    with manager.guard:
        project = load_project(path, request['vod_id'])
        saved = _json(path, f'context/exchange/{export_id}/manifest.json')
        if not saved or saved.get('id') != export_id or saved.get('mode') not in MODES:
            raise ValueError('이 VOD에서 내보낸 외부 작업을 찾을 수 없습니다')
        chunks, replies = saved.get('chunks'), saved.get('replies')
        if (not isinstance(chunks, list) or not chunks or not isinstance(replies, dict)
                or any(not isinstance(c, dict) or not isinstance(c.get('id'), str) for c in chunks)
                or len({c['id'] for c in chunks}) != len(chunks)
                or not set(replies) <= {c['id'] for c in chunks} or type(saved.get('cancelled')) is not bool):
            raise ValueError('외부 작업의 수신 기록을 확인하세요. 기존 자료는 유지됩니다')
        catalog = _json(path, 'context/state.json')
        run = saved.get('latest_run')
        registered = next((r for r in catalog.get('runs', []) if r.get('id') == run
                           and r.get('scope') == 'external' and r.get('mode') == saved['mode']), None)
        try:
            result = _json(path, f'context/runs/{_id(run)}/result.json') if run and registered else {}
            valid_result = bool(result and result.get('id') == run and result.get('export_id') == export_id
                                and result.get('scope') == 'external' and result.get('origin') == 'external'
                                and result.get('mode') == saved['mode'] and result.get('complete') is (len(replies) == len(chunks)))
            if valid_result:
                source = _json(path, f'context/runs/{run}/source.json')
                work = _json(path, f'context/runs/{run}/work.json')
                valid_result = bool(source and work.get('chunks') == chunks and work.get('replies') == replies
                                    and result.get('fingerprint') == saved.get('fingerprint')
                                    and context_exchange_data.fingerprint(source) == saved.get('fingerprint'))
        except (OSError, ValueError, TypeError, KeyError):
            valid_result = False
    received, total = len(replies), len(chunks)
    cancelled, mode = saved['cancelled'], saved['mode']
    stale = context_exchange_data.stale(path, request['vod_id'], saved)
    state = 'cancelled' if cancelled else 'complete' if received == total else 'partial' if received else 'queued'
    if not cancelled and (stale or received and not valid_result):
        state = 'review'
    message = '가져오기 완료. 외부 결과의 형식만 확인했으므로 원문을 검토하세요.' if received == total else '남은 결과 파일을 가져오면 정상 수신분을 보존하고 새 결과 버전을 만듭니다.'
    if cancelled:
        message = '외부 결과 대기를 취소했습니다. 원본과 가져온 결과는 유지됩니다.'
    if stale:
        message += ' 입력이 변경되었거나 없어 현재 자료로 다시 내보내야 합니다.'
    elif received and not valid_result:
        message += ' 연결된 결과 버전을 찾을 수 없습니다. 결과 파일을 다시 가져올 수 있습니다.'
    out.update(title=project.get('metadata', {}).get('title') or request['vod_id'], label='외부 AI ' + MODES[mode],
               export_id=export_id, received=received, total=total, cancelled=cancelled, run=run if valid_result else None,
               mode=mode, state=state, message=message, owned=False, timing=None,
               progress={'fraction': received / total, 'label': f'{received} / {total}묶음 수신'},
               workspace={'root': str(path.parent), 'vod_id': request['vod_id'], 'step': 8, 'export_id': export_id},
               record_note='외부 AI 서비스의 실행 시간과 실제 처리 진행률은 기록하지 않습니다.',
               records=[{'at': saved.get('created_at'), 'state': None, 'message': '외부 분석 자료를 만들었습니다.'}])
    _field(out, 'VOD 번호', request['vod_id'])
    _field(out, '분석 모드', MODES[mode])
    _field(out, '입력 자료', str(saved.get('input_label') or '').replace(chr(183), '/'))
    _field(out, '채팅 포함', '포함' if saved.get('include_chat') else '미포함')
    _field(out, '입력 일치', '확인 필요' if stale else '내보낼 때와 일치')
    if valid_result:
        out['result'] = {'root': str(path.parent), 'vod_id': request['vod_id'], 'step': 6, 'run': run, 'mode': mode}
    if cancelled and received < total and not stale and saved.get('revision') == context_exchange_data.REVISION:
        out['actions'].append({'label': '외부 결과 대기 재개', 'action': 'context-exchange-resume',
                               'data': {'root': str(path.parent), 'vod_id': request['vod_id'], 'export_id': export_id}})
    return out
