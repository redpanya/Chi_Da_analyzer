"""화면용 읽기 전용 보관함 요약. 모델 검사·프로젝트 복구·원본 쓰기를 하지 않는다."""
import os
import re
import shutil
from pathlib import Path

from . import download_scope, automation_plan
from .storage import library, load_project, read_json


def _state(path, name):
    folder = path / name
    if folder.is_symlink():
        raise ValueError('연결 폴더는 읽지 않습니다')
    file = folder / 'state.json'
    value = read_json(file) if file.exists() else {}
    if not isinstance(value, dict):
        raise ValueError('작업 상태가 올바르지 않습니다')
    return {key: value[key] for key in ('state', 'message', 'progress', 'timing', 'run', 'runs', 'updated_at') if key in value}


def _external_results(path, context):
    from .context_job import local
    exports = {}
    runs = context.get('runs', [])
    if not isinstance(runs, list):
        return []
    for entry in reversed(runs):
        if not isinstance(entry, dict) or entry.get('scope') != 'external':
            continue
        run = entry.get('id')
        if not isinstance(run, str) or not re.fullmatch(r'[a-f0-9]{32}', run):
            continue
        try:
            # 목록 조회에서는 큰 전사나 수신 본문 대신 결과 메타데이터만 읽는다.
            value = read_json(local(path, f'runs/{run}/result.json'))
            export = value.get('export_id')
            if (value.get('scope') != 'external' or value.get('id') != run
                    or value.get('mode') not in ('detail', 'timestamps', 'clips')
                    or not isinstance(export, str) or not re.fullmatch(r'[a-f0-9]{32}', export)):
                continue
            if export not in exports:
                exports[export] = {key: value.get(key) for key in ('export_id', 'mode', 'created_at', 'input_label')}
                exports[export].update(run=run, state='complete' if value.get('complete') is True else 'partial')
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return list(exports.values())


def catalog(root):
    base = library(root)
    result = {'root': str(base), 'status': 'ready', 'projects': [], 'warnings': []}
    if not base.exists():
        return result | {'status': 'missing', 'message': '보관함에 연결할 수 없습니다. 외장 디스크와 설정의 폴더 경로를 확인하세요.'}
    if not base.is_dir():
        return result | {'status': 'invalid', 'message': '보관함 경로가 폴더가 아닙니다.'}
    try:
        # glob의 권한 오류 묵살을 피한다.
        with os.scandir(base) as entries:
            next(entries, None)
        for path in download_scope.project_paths(base):
            if path.is_symlink() or not (path / 'project.json').exists():
                continue
            try:
                data = load_project(path, path.name.removeprefix('vod-'))
                if (not isinstance(data.get('metadata'), dict) or not isinstance(data['metadata'].get('title'), str)
                        or any(not isinstance(data['tasks'].get(key), dict) for key in ('video', 'chat'))):
                    raise ValueError('등록 정보의 형식을 확인하세요')
                row = {key: data[key] for key in ('vod_id', 'metadata', 'tasks', 'download_range', 'updated_at', 'input') if key in data}
                replacement = data.get('video_replacement')
                if isinstance(replacement, dict) and isinstance(replacement.get('task'), dict):
                    row['video_replacement'] = {'task': replacement['task']}
                row.update(path=str(path), root=str(path.parent), library_root=str(base))
                row['summaries'] = {}
                for name in ('speech', 'voices', 'context'):
                    try:
                        row['summaries'][name] = _state(path, name)
                    except (OSError, ValueError, TypeError):
                        row['summaries'][name] = {'state': 'error', 'message': '상태 파일 확인 필요 · 기존 자료 보존'}
                row['external_results'] = _external_results(path, row['summaries']['context'])
                result['projects'].append(row)
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                result['warnings'].append(path.name + ': 등록 정보를 읽지 못했습니다. 파일은 유지됩니다.')
    except PermissionError:
        return result | {'status': 'permission', 'message': '보관함 읽기 권한을 확인하세요.'}
    result['projects'].sort(key=lambda row: row.get('updated_at') if isinstance(row.get('updated_at'), str) else '', reverse=True)
    if not result['projects']:
        result['status'] = 'partial' if result['warnings'] else 'empty'
    elif result['warnings']:
        result['status'] = 'partial'
    return result


def storage_info(root):
    base = library(root)
    if not base.is_dir():
        raise ValueError('보관함이 연결되지 않았습니다')
    sizes = {'영상': 0, '채팅': 0, '전사·화자': 0, '분석·편집': 0, '기타': 0}
    unreadable = 0
    def error(_):
        nonlocal unreadable
        unreadable += 1
    for directory, folders, files in os.walk(base, followlinks=False, onerror=error):
        folders[:] = [name for name in folders if not (Path(directory) / name).is_symlink()]
        for name in files:
            file = Path(directory) / name
            if file.is_symlink():
                continue
            parts = file.relative_to(base).parts
            category = ('영상' if 'media' in parts else '채팅' if 'chat-pages' in parts or 'exports' in parts
                        else '전사·화자' if 'speech' in parts or 'voices' in parts else '분석·편집'
                        if any(part in parts for part in ('context', 'analysis', 'studio')) else '기타')
            try:
                sizes[category] += file.stat().st_size
            except OSError:
                unreadable += 1
    return {'sizes': sizes, 'free': shutil.disk_usage(base).free, 'unreadable': unreadable}


def preflight(manager, root):
    """준비 상태는 안내용 스냅샷이다. 실제 실행기의 재검증을 대체하지 않는다."""
    from . import speech_model, context_model, speaker_tools
    from . import voice_models
    base = library(root)
    data = manager.automation.read(str(base))
    items = [item for item in data['items'] if item.get('state') in ('queued', 'paused', 'running')]
    steps = set(step for item in items for step in automation_plan.selected(item['options']))
    checks = []
    def add(label, ready, detail):
        checks.append({'label': label, 'ready': bool(ready), 'detail': detail})
    add('보관함', base.is_dir(), '외장 디스크 연결과 쓰기 권한은 실행 시 다시 확인합니다.')
    if base.is_dir():
        checks.append({'label': '남은 저장 공간', 'ready': True, 'detail': f'{shutil.disk_usage(base).free / 1024**3:.1f} GiB · 출력 크기는 입력과 설정에 따라 달라집니다.'})
    if steps & {'download', 'audio', 'transcribe'}:
        add('영상·음성 도구', shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg / ffprobe')
    if 'transcribe' in steps:
        state = speech_model.status()
        add('전사 모델·도구', state['ready'] and state['engine'], '음성 전사 → 새 전사에서 준비할 수 있습니다.')
    if 'context' in steps:
        state = context_model.status(context_model.DEFAULT_NAME)
        add('Gemma 모델·도구', state['ready'] and state['engine'], '장면 탐색 → 새 분석에서 모델을 준비하세요.')
    for backend in dict.fromkeys(item['options'].get('backend', 'sherpa') for item in items if 'diarize' in automation_plan.selected(item['options'])):
        ready = speaker_tools.supported(backend) and speaker_tools.resolve(backend)[0].is_file()
        if backend == 'sherpa': ready = ready and voice_models.status()['ready']
        add('화자 도구 · ' + backend, ready, '화자 검토에서 모델·인증을 확인하세요. Community-1 이용 동의 여부는 여기서 검사하지 않습니다.')
    return {'checks': checks, 'items': [{'title': item['title'], 'preview': item.get('preview', '완료 자료 확인 후 선택 단계만 진행')} for item in items]}
