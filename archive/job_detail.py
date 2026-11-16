"""작업 상세 조회와 저장된 설정을 이용한 재개. 다른 실행의 기록을 추측해 연결하지 않는다."""
from copy import deepcopy
import math
import re

from . import automation_plan, download_scope, task_timing
from .storage import Conflict, library, load_project, project_path, read_json

LABELS = {'video': '영상 다운로드', 'chat': '채팅 다운로드', 'speech': '음성 처리',
          'voices': '화자 구분', 'context': 'AI 문맥 분석', 'queue': '순차 작업', 'heavy': '대기열 작업'}
STAGES = {'download': '영상과 채팅', 'audio': '원음 추출', 'transcribe': '음성 전사',
          'diarize': '화자 구분', 'reactions': '채팅 반응', 'summary': '상세 문맥',
          'timestamps': '타임스탬프', 'clips': '클립 후보', 'context': 'AI 문맥'}
MODES = {'detail': '상세 문맥', 'timestamps': '타임스탬프', 'clips': '클립 후보'}
ACTIVE = task_timing.ACTIVE | {'starting'}


def _id(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{32}', value):
        raise ValueError('작업 또는 결과 번호가 올바르지 않습니다')
    return value


def _json(path, relative):
    target = path / relative
    for part in (target, *target.parents):
        if part == path:
            break
        if part.is_symlink():
            raise Conflict('연결 파일은 작업 상세 자료로 사용할 수 없습니다')
    if not target.exists():
        return {}
    value = read_json(target)
    if not isinstance(value, dict):
        raise ValueError('작업 정보의 형식을 확인하세요')
    return value


def _field(out, label, value):
    if value is not None and value != '':
        out['fields'].append({'label': label, 'value': str(value)})


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _progress(value):
    value = value if isinstance(value, dict) else {}
    if value.get('phase') and _number(value.get('percent')):
        label = f"{value['percent']:g}%"
        if value['phase'] == 'receive' and _number(value.get('speed')):
            label += f" / 수신 속도 {value['speed']/1e6:.2f} MB/초"
        elif _number(value.get('processing_rate')):
            label += f" / 처리 속도 {value['processing_rate']:.2f}배속"
        return {'fraction': min(1,value['percent']/100), 'label':label}
    for done, total, unit in [('downloaded_bytes', 'total_bytes', '바이트'),
                              ('processed_ms', 'duration_ms', '시간'), ('done', 'total', '처리')]:
        a, b = value.get(done), value.get(total)
        if _number(a) and _number(b) and b:
            if unit == '시간':
                label = download_scope.timecode(round(a)) + ' / ' + download_scope.timecode(round(b))
            elif unit == '바이트':
                label = f'{a / 1048576:,.1f} / {b / 1048576:,.1f} MB'
            else:
                label = f'{a:,} / {b:,}'
            return {'fraction': min(1, a / b), 'label': label}
    if _number(value.get('percent')):
        return {'fraction': min(1, value['percent'] / 100), 'label': f"{value['percent']:g}%"}
    return None


def _worker(manager, kind, path):
    return manager.tasks.find({'video': 'download', 'chat': 'download'}.get(kind, kind), path)


def _status(out, value, owned):
    out.update(state=value.get('state', 'idle'), message=str(value.get('message') or ''), owned=owned,
               progress=_progress(value.get('progress')), timing=deepcopy(value.get('timing')))
    if not owned and out['state'] in ACTIVE:
        out['state'] = 'paused'
        out['message'] = '이전 실행 상태입니다. 이 실행기에서 진행 중인 작업은 확인되지 않습니다. ' + out['message']
        out['timing'] = task_timing.interrupted(value).get('timing')


def _settings(out, value, steps=None):
    from .analysis_inputs import LANGUAGES, VAD
    from .diarization_backends import BACKENDS
    value = dict(value)
    if steps is not None:
        for step, keys in {'download': ('height', 'quality'), 'transcribe': ('language', 'asr_options'),
                           'diarize': ('backend', 'backend_label'), 'context': ('thinking', 'inference', 'summary_modes')}.items():
            if step not in steps:
                for key in keys:
                    value.pop(key, None)
    for key, label in [('model', '모델'), ('input_label', '입력 자료'), ('quality', '다운로드 화질')]:
        _field(out, label, value.get(key))
    _field(out, '언어', LANGUAGES.get(value.get('language'), value.get('language')))
    backend = value.get('backend_label') or BACKENDS.get(value.get('backend'), {}).get('label') or value.get('backend')
    _field(out, '화자 엔진', backend.split(chr(183), 1)[0].strip() if backend else None)
    options = value.get('asr_options') or {}
    vad = VAD.get(options.get('vad'), options.get('vad'))
    _field(out, '발화 검출', vad.removeprefix('발화 검출 ') if isinstance(vad, str) else vad)
    if 'height' in value:
        _field(out, '최대 화질', str(value['height']) + 'p')
    inference = value.get('inference') or value
    if type(inference.get('thinking')) is bool:
        _field(out, '사고 모드', '켜기' if inference['thinking'] else '끄기')
    if isinstance(value.get('summary_modes'), list):
        _field(out, 'AI 분석 모드', ', '.join(MODES.get(m, m) for m in value['summary_modes']))


def _report_records(manager, path, report):
    value = manager.reports.read(str(path.parent), path.name[4:], _id(report))
    if value.get('payload', {}).get('vod_id') != path.name[4:]:
        raise Conflict('작업 리포트의 VOD가 일치하지 않습니다')
    records = []
    for row in value.get('events', []):
        if not isinstance(row, dict) or not row.get('at'):
            continue
        label = STAGES.get(row.get('stage'), row.get('stage', '작업'))
        records.append({'at': row['at'], 'message': label + ': ' + str(row.get('message') or row.get('state') or ''),
                        'state': row.get('state')})
    return records[-5:]


def _queue(manager, request, out):
    requested_root = library(request['root']); base = download_scope.base_root(requested_root)
    automation = manager.automation
    with automation.guard:
        data = automation.read(str(base))
        entry = next((i for i in [*data['items'], *data.get('results', [])] if i.get('id') == _id(request.get('id'))), None)
        if not entry or (request.get('vod_id') and entry.get('vod') != request['vod_id']):
            raise Conflict('선택한 보관함의 순차 작업이 아닙니다')
        entry = deepcopy(entry)
        root = library(download_scope.entry_root(base, entry))
        if requested_root != base and requested_root != root:
            raise Conflict('선택한 구간의 순차 작업이 아닙니다')
        owned = bool(automation.running and automation.root == str(base) and entry['id'] in automation.active)
    _status(out, entry, owned or entry.get('state') == 'queued')
    out['owned'] = owned
    out['title'] = entry.get('title') or out['title']
    out['workspace'] = {'root': str(root), 'vod_id': entry['vod'], 'step': 2}
    _field(out, 'VOD 번호', entry['vod'])
    options = entry.get('options') or {}
    _settings(out, options, steps=automation_plan.selected(options))
    _field(out, '현재 단계', STAGES.get(entry.get('stage'), entry.get('stage')))
    outcomes = entry.get('stages') or {}
    for stage, status in outcomes.items():
        _field(out, STAGES.get(stage, stage), {'complete': '완료', 'reused': '재사용', 'skipped': '건너뜀', 'partial': '일부 완료'}.get(status, status))
    if entry.get('report'):
        try:
            out['records'] = _report_records(manager, project_path(root, entry['vod']), entry['report'])
            out['record_note'] = '이 순차 작업에 연결된 실행 기록입니다.'
        except (OSError, ValueError, TypeError, KeyError):
            out['record_note'] = '연결된 리포트를 읽을 수 없습니다. 기존 기록은 변경하지 않았습니다.'
    if not out['records'] and entry.get('message'):
        out['records'] = [{'at': None, 'message': entry['message'], 'state': entry.get('state')}]
    if (project_path(root, entry['vod']) / 'project.json').is_file():
        out['result'] = dict(out['workspace'])
    if owned and entry.get('state') in ACTIVE:
        out['actions'].append({'label': '이 항목 중단', 'action': 'queue-pause-item', 'data': {'root': str(base), 'id': entry['id']}})
    return out


def _heavy(manager, request, out):
    with manager.guard:
        entry = next((i for i in manager.tasks.items if i.get('id') == _id(request.get('id'))), None)
        if not entry:
            raise ValueError('이 실행기에 해당 대기열 작업이 없습니다')
        if (request.get('vod_id') and entry.get('vod_id') != request['vod_id']) or (request.get('root') and entry.get('root') and library(entry['root']) != library(request['root'])):
            raise Conflict('선택한 보관함의 대기열 작업이 아닙니다')
        entry = deepcopy(entry)
    _status(out, entry, entry.get('state') in ACTIVE)
    out.update(title=entry.get('title') or out['title'], label=entry.get('label') or out['label'])
    _field(out, 'VOD 번호', entry.get('vod_id'))
    submitted = entry.get('data') or {}
    _settings(out, submitted | (submitted.get('options') or {}))
    if entry.get('root') and entry.get('vod_id'):
        step = {'speech-start': 3, 'voices-start': 4, 'context-start': 6, 'analyze': 5}.get(entry.get('action'), 2)
        out['workspace'] = {'root': entry['root'], 'vod_id': entry['vod_id'], 'step': step}
    _field(out, '등록 시각', entry.get('created_at'))
    if entry.get('message'):
        out['records'] = [{'at': None, 'state': entry.get('state'), 'message': entry['message']}]
    kind = {'speech-start': 'speech', 'voices-start': 'voices', 'context-start': 'context'}.get(entry.get('action'))
    if kind and entry.get('state') == 'running' and out['workspace']:
        path = project_path(entry['root'], entry['vod_id'])
        if _worker(manager, kind, path):
            live = _detail(manager, {'kind': kind, 'root': entry['root'], 'vod_id': entry['vod_id']})
            for key in ('state', 'message', 'progress', 'timing', 'records', 'record_note', 'run', 'mode', 'result', 'owned', 'actions'):
                out[key] = live.get(key)
    if entry.get('state') == 'queued':
        out['actions'].append({'label': '대기 취소', 'action': 'work-cancel', 'data': {'id': entry['id']}})
    return out


def _detail(manager, request):
    kind = request.get('kind')
    if kind not in LABELS and kind != 'external':
        raise ValueError('작업 종류를 확인하세요')
    out = dict(kind=kind, title='작업', label=LABELS.get(kind, '외부 AI 분석'), state='idle', message='', fields=[], records=[],
               record_note='연결된 상세 실행 기록이 없습니다. 확인 가능한 저장 상태만 표시합니다.',
               result=None, workspace=None, run=None, mode=None, owned=False, actions=[])
    if kind == 'external':
        from .job_detail_external import detail as external_detail
        return external_detail(manager, request, out)
    if kind == 'heavy':
        return _heavy(manager, request, out)
    if kind == 'queue':
        return _queue(manager, request, out)
    path = project_path(request['root'], request['vod_id'])
    project = load_project(path, request['vod_id'])
    step = {'video': 2, 'chat': 2, 'speech': 3, 'voices': 4, 'context': 6}[kind]
    out['workspace'] = {'root': str(path.parent), 'vod_id': request['vod_id'], 'step': step}
    out['title'] = project.get('metadata', {}).get('title') or request['vod_id']
    _field(out, 'VOD 번호', request['vod_id'])
    scope = project.get('download_range')
    _field(out, '영상 범위', f"{download_scope.timecode(scope['start_ms'])} ~ {download_scope.timecode(scope['end_ms'])}" if scope else '전체 영상')
    with manager.guard:
        job = _worker(manager, kind, path)
        if kind in ('video', 'chat'):
            value = project['tasks'][kind]
            if kind == 'video' and project.get('video_replacement', {}).get('task'):
                value = project['video_replacement']['task']
        else:
            value = _json(path, kind + '/state.json')
        value = deepcopy(value)
    _status(out, value, bool(job))
    current_run = value.get('pending_run') or (value.get('pending_diarization') or {}).get('id') or value.get('run')
    if ((kind == 'speech' and value.get('action') in ('audio', 'model')) or
            (kind == 'voices' and value.get('action') not in (None, 'diarize')) or
            (kind == 'context' and value.get('action') == 'model')):
        current_run = None
    if kind == 'context' and value.get('action') in ('clips', 'clips-resume'):
        current_run = value.get('clip_run')
    elif kind == 'context' and value.get('action') in ('whole', 'resume'):
        current_run = value.get('full_run')
    selected = request.get('run') or current_run
    if selected:
        _id(selected)
    if selected and kind in ('speech', 'voices', 'context'):
        if kind == 'speech' and selected in value.get('deleted_runs', []):
            raise ValueError('삭제된 전사 결과입니다')
        if kind == 'voices' and selected not in value.get('runs', []) and selected != current_run:
            raise ValueError('저장된 화자 결과가 아닙니다')
        if kind == 'context' and selected not in [r.get('id') for r in value.get('runs', [])]:
            raise ValueError('저장된 문맥 결과가 아닙니다')
        name = 'manifest.json' if kind == 'speech' else 'result.json'
        saved = _json(path, f'{kind}/runs/{selected}/{name}')
        if saved and saved.get('id') != selected:
            raise Conflict('결과 파일의 실행 번호가 일치하지 않습니다')
        if selected != current_run:
            if not saved:
                raise ValueError('선택한 이전 결과 파일을 찾을 수 없습니다')
            out.update(state='complete' if saved.get('complete') or kind == 'voices' else 'partial', message='선택한 이전 결과 버전입니다.',
                       progress=None, timing=None, owned=False)
        out['run'] = selected
        _settings(out, saved)
        _field(out, '결과 생성 시각', saved.get('created_at'))
        if kind == 'speech':
            _field(out, '발언 수', saved.get('segment_count'))
            if saved and not (out['owned'] and selected == current_run and out['progress']):
                out['progress'] = _progress(saved)
        elif kind == 'voices' and saved:
            _field(out, '감지한 화자 수', len(saved.get('speakers') or {}))
            assignments = saved.get('assignments') or {}
            _field(out, '원래 배정 발언 수', sum(1 for row in assignments.values() if row.get('speaker') is not None))
            _field(out, '원래 미배정 발언 수', sum(1 for row in assignments.values() if row.get('speaker') is None))
        elif kind == 'context':
            entry = next((r for r in value.get('runs', []) if r.get('id') == selected), {})
            out['mode'] = saved.get('mode') or entry.get('mode') or ('clips' if entry.get('scope') == 'clips-local' else 'timestamps' if entry.get('scope') == 'timestamps' else 'detail')
            _field(out, '분석 모드', MODES.get(out['mode'], out['mode']))
            if isinstance(saved.get('items'), list):
                _field(out, '보존한 항목 수', len(saved['items']))
            if saved.get('origin') == 'external' or saved.get('scope') == 'external':
                # 파일 가져오기는 선택 결과만 바꾸므로 과거 로컬 작업 상태를 연결하면 안 된다.
                out.update(state='complete' if saved.get('complete') else 'partial', owned=False,
                           message='외부 AI에서 가져온 결과입니다. 수신 상태는 외부 AI 작업 상세에서 확인하세요.',
                           progress=None, timing=None, records=[],
                           record_note='이 결과에 이전 로컬 분석의 실행 기록을 연결하지 않습니다.')
                out['result'] = out['workspace'] | {'run': selected, 'mode': out['mode']}
                out['workspace'] = out['workspace'] | {'step': 8}
                if saved.get('export_id'):
                    out['workspace']['export_id'] = _id(saved['export_id'])
                return out
        # 전사와 화자 버전 선택은 쓰기 작업이다. 실행 중에는 현재 선택본만 바로 열 수 있다.
        can_select = kind != 'voices' or selected in value.get('runs', [])
        if saved and can_select and not (kind in ('speech', 'voices') and job and selected != value.get('run')):
            out['result'] = out['workspace'] | {'run': selected, 'mode': out['mode']}
    elif kind in ('video', 'chat'):
        out['result'] = dict(out['workspace'])
    if kind == 'video':
        format_id = (project.get('video_replacement') or {}).get('format_id') or project.get('format_id')
        quality = next((r for r in project.get('metadata', {}).get('formats', []) if r.get('id') == format_id), {})
        _field(out, '화질', quality.get('label') or (str(quality['height']) + 'p' if quality.get('height') else None))
    if kind == 'chat':
        for key, label in [('messages', '수집 채팅 수'), ('pages', '받은 페이지 수')]:
            _field(out, label, (value.get('progress') or {}).get(key))
    if kind == 'speech' and not selected:
        audio = value.get('raw_audio') or value.get('audio') or {}
        if _number(audio.get('duration_ms')):
            _field(out, '추출한 원음 길이', download_scope.timecode(round(audio['duration_ms'])))
            out['result'] = dict(out['workspace'])
    if not request.get('run') or selected == current_run:
        if value.get('message'):
            out['records'] = [{'at': value.get('updated_at'), 'message': value['message'], 'state': value.get('state')}]
        if out['owned'] and out['state'] in ACTIVE:
            action = 'stop' if kind in ('video', 'chat') else kind + '-stop'
            data = {'root': str(path.parent), 'vod_id': request['vod_id']}
            if action == 'stop':
                data['kind'] = kind
            out['actions'].append({'label': '작업 중단', 'action': action, 'data': data})
    return out


RESUMABLE = {'paused', 'error', 'partial', 'review', 'cancelled'}


def _snapshot(manager, path, kind, value):
    saved = value.get('resume_request')
    if isinstance(saved, dict) and saved.get('action') == value.get('action'):
        return deepcopy(saved)
    # 이번 실행기에 남아 있는 작업 객체도 그 실행의 정확한 요청이다.
    job = getattr(manager, 'speech_job' if kind == 'speech' else 'voice_job', None)
    if (job and getattr(job, 'path', None) == path and getattr(job, 'action', None) == value.get('action')
            and isinstance(getattr(job, 'options', None), dict)):
        return {'action': job.action, 'options': deepcopy(job.options)}
    return None


def _resume_plan(manager, request, out):
    kind = request['kind']
    if out['state'] not in RESUMABLE or out['owned']:
        raise Conflict('중단되거나 실패한 작업만 이어서 처리할 수 있습니다')
    if kind == 'queue':
        base = download_scope.base_root(library(request['root']))
        if manager.automation.running or any(i.get('state') in ('queued', 'starting', 'running') and
                i.get('action') == 'queue-start' and library(i['data']['root']) == base for i in manager.tasks.items):
            raise Conflict('이 목록의 순차 작업이 이미 실행 또는 대기 중입니다')
        return 'queue-start', {'root': str(base)}
    if kind == 'heavy':
        entry = next(i for i in manager.tasks.items if i.get('id') == request['id'])
        action, data = entry['action'], deepcopy(entry['data'])
        # 생성 요청을 반복하면 새 결과가 생기는 작업은 기존 실행 번호로만 재개한다.
        if action.startswith(('studio-', 'split-')):
            if not entry.get('run'):
                raise Conflict('이어갈 실행 번호가 없습니다. 기존 작업 화면에서 확인하세요')
            action = 'studio-resume' if action.startswith('studio-') else 'split-resume'
            data = ({'root': data['root'], 'vod_id': data['vod_id'], 'run': entry['run']} if action == 'studio-resume'
                    else {'id': entry['run']})
        elif action not in ('start', 'speech-start', 'voices-start', 'context-start', 'analyze'):
            raise Conflict('이 작업은 기존 작업 화면에서 현재 자료를 확인한 뒤 진행하세요')
        if 'vod_id' in data:
            path = project_path(data['root'], data['vod_id'])
            if entry.get('identity') is not None and manager.tasks.identity(path) != entry['identity']:
                raise Conflict('작업 이후 영상 또는 프로젝트가 변경됐습니다. 현재 자료를 확인하세요')
        if action in ('speech-start', 'voices-start', 'context-start'):
            exact_run = (data.get('options') or {}).get('run') if action == 'context-start' else None
            if not exact_run:
                raise Conflict('이 대기 기록의 실행 결과를 정확히 연결할 수 없습니다. 해당 VOD 작업의 상세에서 이어서 처리하세요')
            subrequest = {'root': data['root'], 'vod_id': data['vod_id'], 'kind': 'context', 'run': exact_run}
            return _resume_plan(manager, subrequest, _detail(manager, subrequest))
        return action, data
    path = project_path(request['root'], request['vod_id'])
    data = {'root': str(path.parent), 'vod_id': request['vod_id']}
    if kind in ('video', 'chat'):
        project = load_project(path, request['vod_id'])
        if not project.get('format_id'):
            raise Conflict('저장된 다운로드 화질을 찾을 수 없습니다. 영상 설정에서 확인하세요')
        return 'start', data | {'kind': kind, 'format_id': project['format_id']}
    value = _json(path, kind + '/state.json')
    run = out.get('run')
    saved = _json(path, f'{kind}/runs/{run}/' + ('manifest.json' if kind == 'speech' else 'result.json')) if run else {}
    if saved.get('complete') and (kind == 'context' or kind == 'speech' and value.get('action') == 'transcribe'):
        raise Conflict('이미 완료된 결과입니다. 결과 보기를 사용하세요')
    if kind == 'context':
        scope = saved.get('scope') or next((r.get('scope') for r in value.get('runs', []) if r.get('id') == run), None)
        action = {'full': 'resume', 'timestamps': 'timestamps-resume', 'clips-local': 'clips-resume'}.get(scope)
        if saved.get('origin') == 'external' or scope == 'external':
            raise Conflict('외부 AI 결과는 남은 응답 파일을 가져와 이어서 정리하세요')
        if not action or not saved:
            raise Conflict('이어갈 분석 자료를 찾을 수 없습니다. 새 분석에서 설정을 확인하세요')
        return 'context-start', data | {'action': action, 'options': {'run': run}}
    snapshot = _snapshot(manager, path, kind, value)
    if kind == 'speech':
        action = value.get('action')
        if action == 'transcribe' and saved:
            current = value.get('pending_run') or value.get('run')
            if run != current:
                raise Conflict('이전 전사 버전은 전사 설정에서 확인하세요. 현재 중단된 실행만 직접 이어갑니다')
            from .speech_store import input_info
            info = input_info(saved)
            raw = value.get('raw_audio') or value.get('audio') or {}
            if info['input_kind'] != 'original' or not raw.get('sha256') or raw['sha256'] != saved.get('source_audio_sha256', saved.get('audio_sha256')):
                raise Conflict('원음 입력이 변경되었거나 이전 분리음 전사입니다. 전사 설정에서 확인하세요')
            if not saved.get('language'):
                raise Conflict('저장된 전사 언어를 확인할 수 없습니다')
            if snapshot:
                options = snapshot.get('options') or {}
                if (options.get('language') != saved['language'] or options.get('input_kind', 'original') != info['input_kind']
                        or options.get('asr_options') != info['asr_options']):
                    raise Conflict('마지막 요청과 보존한 전사 실행의 설정이 다릅니다. 전사 설정에서 확인하세요')
            return 'speech-start', data | {'action': 'transcribe', 'language': saved['language'],
                                           'input_kind': 'original', 'asr_options': info['asr_options']}
        if snapshot and action in ('audio', 'model', 'transcribe'):
            options = snapshot['options']
            if action == 'audio' and type(options.get('track')) is not int:
                raise Conflict('저장된 오디오 트랙을 확인할 수 없습니다')
            return 'speech-start', data | {k: options[k] for k in ('track', 'language', 'input_kind', 'asr_options') if k in options} | {'action': action}
    elif kind == 'voices':
        action = value.get('action')
        pending = value.get('pending_diarization') or {}
        if action == 'diarize' and pending.get('id') == run and pending.get('signature'):
            signature = pending['signature']; speech = _json(path, 'speech/state.json')
            audio = speech.get('audio') or {}
            if speech.get('run') != signature.get('transcript_run') or audio.get('sha256') != signature.get('audio_sha256'):
                raise Conflict('화자 분석의 원음 또는 전사 입력이 바뀌었습니다. 화자 설정에서 확인하세요')
            options = {'backend': signature.get('backend', 'sherpa'), 'speakers': signature['speakers']}
            if snapshot and any(snapshot['options'].get(key, 'sherpa' if key == 'backend' else -1) != options[key]
                                for key in ('backend', 'speakers')):
                raise Conflict('마지막 요청과 보존한 화자 실행의 설정이 다릅니다. 화자 설정에서 확인하세요')
            return 'voices-start', data | {'action': action, 'options': options}
        if snapshot and action in ('prepare', 'install-engine', 'check-engine', 'diarize', 'suggest', 'retranscribe-original'):
            return 'voices-start', data | snapshot
    raise Conflict('이전 실행의 정확한 설정이 남아 있지 않습니다. 작업 화면에서 설정을 확인하세요')


def detail(manager, request):
    with manager.guard:
        out = _detail(manager, request)
        if request['kind'] != 'external' and out['state'] in RESUMABLE and not out['owned']:
            try:
                _resume_plan(manager, request, out)
            except (Conflict, ValueError, KeyError, OSError) as error:
                out['resume_note'] = str(error)
            else:
                identity = {k: request[k] for k in ('root', 'vod_id', 'kind', 'id') if k in request}
                if out.get('run'):
                    identity['run'] = out['run']
                out['actions'].append({'label': '이어서 처리', 'action': 'job-resume', 'data': identity})
        return out


def resume(manager, request):
    """버튼에 담긴 설정을 신뢰하지 않고 현재 저장본에서 다시 구성한다."""
    with manager.guard:
        out = _detail(manager, request)
        action, data = _resume_plan(manager, request, out)
        if request['kind'] == 'queue':
            entry = next(i for i in manager.automation.read(data['root'])['items'] if i['id'] == request['id'])
            if entry['state'] != 'running':
                manager.automation.remove_or_retry(data['root'], request['id'], retry=True)
        result = manager.tasks.submit(action, data)
        return {'message': '앞 작업 뒤에 이어서 처리하도록 대기열에 등록했습니다' if result.get('queued')
                else '저장한 설정으로 이어서 처리를 시작했습니다',
                **({'queued': result['queued']} if result.get('queued') else {})}
