"""전체 보관함과 충돌하지 않는 원격 구간 프로젝트의 범위·경로 계약."""
import hashlib
import json
import math
import re

from .storage import Conflict, library, project_path, ProjectLock, create_or_load, load_project, save_json


def validate(value, duration=None):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {'start_ms', 'end_ms'}:
        raise ValueError('다운로드 시작·끝 시각을 확인하세요')
    a, b = value['start_ms'], value['end_ms']
    if type(a) is not int or type(b) is not int or a < 0 or b-a < 1000 or b-a > 20*3600000:
        raise ValueError('다운로드 구간은 시작보다 끝이 늦어야 하며 1초 이상, 최대 20시간입니다')
    if duration is not None:
        if not isinstance(duration, (int, float)) or not math.isfinite(duration) or b > round(duration*1000):
            raise ValueError('다운로드 끝 시각이 VOD 길이를 넘습니다')
    return dict(start_ms=a, end_ms=b)


def bounds(data):
    return validate(data.get('download_range'), data['metadata'].get('duration'))


def remote(data):
    return data.get('download_range') is not None


def timecode(ms):
    seconds = ms//1000
    return f'{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}'


def checked_root(base, candidate=None):
    base = library(str(base))
    if candidate is None or str(base) == str(candidate):
        return base
    from pathlib import Path
    raw = Path(candidate)
    if raw.parent != base/'.download-ranges' or not re.fullmatch('[0-9a-f]{32}', raw.name):
        raise ValueError('현재 보관함의 저장 자료를 선택하세요')
    if raw.is_symlink() or raw.parent.is_symlink():
        raise Conflict('구간 저장 폴더에 연결 경로를 사용할 수 없습니다')
    return raw


def range_root(base, vod, scope, format_id):
    key = hashlib.sha256(json.dumps([vod, scope, format_id], sort_keys=True).encode()).hexdigest()[:32]
    return checked_root(base, library(str(base))/'.download-ranges'/key)


def entry_root(base, entry):
    return str(checked_root(base, entry.get('project_root')))


def base_root(root):
    root = library(str(root))
    if root.parent.name == '.download-ranges' and re.fullmatch('[0-9a-f]{32}', root.name):
        return root.parent.parent
    return root


def project_paths(base):
    base = library(str(base))
    yield from base.glob('vod-*')
    folder = base/'.download-ranges'
    if folder.is_symlink():
        return
    for root in folder.glob('*'):
        if re.fullmatch('[0-9a-f]{32}', root.name) and not root.is_symlink():
            yield from root.glob('vod-*')


def prepare(base, meta, settings, source_root=None):
    """등록/미실행 설정 변경에서만 호출한다. 이미 받은 자료는 덮어쓰지 않는다."""
    source_root = checked_root(base, source_root)
    scope = validate(settings.get('download_range'), meta.get('duration'))
    if scope is not None and not isinstance(meta.get('duration'), (int, float)):
        raise ValueError('구간 다운로드를 위해 VOD 길이 확인이 필요합니다')
    if scope:
        candidates = [f for f in meta.get('formats', []) if 0 < (f.get('height') or 0) <= settings['height']]
        if not candidates:
            raise ValueError(f"선택한 최대 화질 {settings['height']}p 이하의 영상이 없습니다")
        selected = max(candidates, key=lambda f:(f['height'], f.get('fps') or 0))
        target_root = range_root(base, meta['id'], scope, selected['id'])
    else:
        target_root = source_root
    path = project_path(target_root, meta['id'])
    with ProjectLock(path):
        if (path/'project.json').exists():
            data = load_project(path, meta['id'])
            if scope and (bounds(data) != scope or data['format_id'] != selected['id']):
                raise Conflict('저장된 구간 설정이 다릅니다. 기존 자료를 보존했습니다')
            return str(target_root), data
        if not scope:
            if meta.get('source_title'):
                meta = meta | {'title':meta['source_title']}
            candidates = [f for f in meta.get('formats', []) if 0 < (f.get('height') or 0) <= settings['height']]
            if not candidates:
                raise ValueError(f"선택한 최대 화질 {settings['height']}p 이하의 영상이 없습니다")
            selected = max(candidates, key=lambda f:(f['height'], f.get('fps') or 0))
            return str(target_root), create_or_load(path, meta, selected['id'])
        title = meta.get('source_title', meta['title'])
        range_meta = meta | {'source_title':title, 'title':f'{title} · 구간 {timecode(scope["start_ms"])}–{timecode(scope["end_ms"])} · {selected["height"]}p'}
        data = create_or_load(path, range_meta, selected['id'], {'kind':'range', 'start_vod_ms':scope['start_ms'],
                             'end_vod_ms':scope['end_ms'], 'parent_vod':meta['id']})
        data['download_range'] = scope
        save_json(path/'project.json', data)
        return str(target_root), data
