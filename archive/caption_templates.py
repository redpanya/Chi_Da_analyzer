"""VOD와 독립적인 자막 색상·효과 템플릿. 적용된 초안은 값의 사본을 보존한다."""
import re
import unicodedata
import uuid
from . import caption_design, runtime
from .storage import Conflict, ProjectLock, read_json, save_json, stamp


def folder():
    path = runtime.SUPPORT/'caption-templates'
    if path.is_symlink():raise ValueError('자막 템플릿 폴더에 연결 경로를 사용할 수 없습니다')
    return path


def template_id(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{32}', value):
        raise ValueError('저장한 자막 템플릿을 선택하세요')
    return value


def template_name(value):
    if not isinstance(value, str):raise ValueError('템플릿 이름을 입력하세요')
    value = unicodedata.normalize('NFC', value.strip())
    if not 1 <= len(value) <= 60 or any(unicodedata.category(c).startswith('C') for c in value):
        raise ValueError('템플릿 이름은 줄바꿈 없이 1~60자로 입력하세요')
    return value


def entries():
    result = []
    for file in folder().glob('*.json'):
        try:item = read_json(file)
        except FileNotFoundError:continue  # 다른 창에서 목록 조회 중 제거할 수 있다.
        if not isinstance(item, dict) or item.get('schema') != 1 or item.get('id') != file.stem:
            raise ValueError('저장한 자막 템플릿을 읽지 못했습니다. 기존 파일을 확인하세요')
        template_id(item['id']);template_name(item.get('name'))
        if item.get('style') not in ('basic', 'box') or caption_design.validate(item.get('design')) is None:
            raise ValueError('저장한 자막 템플릿의 색상·효과 설정을 확인하세요')
        result.append(item)
    return sorted(result, key=lambda item:(item['name'].casefold(), item['id']))


def dispatch(action, data):
    if action == 'list':return {'templates':entries()}
    path = folder()
    with ProjectLock(path):
        current = entries()
        if action == 'save':
            name = template_name(data.get('name'))
            if any(item['name'].casefold() == name.casefold() for item in current):
                raise Conflict('같은 이름의 템플릿이 있습니다. 다른 이름을 입력하세요')
            design = caption_design.validate(data.get('design'))
            if design is None:raise ValueError('저장할 색상·효과를 먼저 선택하세요')
            item = dict(schema=1, id=uuid.uuid4().hex, name=name, style='box' if design['box'] else 'basic',
                        design=design, created_at=stamp())
            save_json(path/(item['id']+'.json'), item)
            return {'templates':entries(), 'id':item['id']}
        if action == 'delete':
            id = template_id(data.get('id'))
            if not any(item['id'] == id for item in current):
                raise Conflict('이미 제거된 템플릿입니다. 목록을 다시 불러오세요')
            removed = path/'deleted'
            if removed.is_symlink():raise ValueError('템플릿 삭제 보관 경로를 확인하세요')
            removed.mkdir(exist_ok=True)
            (path/(id+'.json')).rename(removed/(id+'-'+uuid.uuid4().hex+'.json'))
            return {'templates':entries()}
        raise ValueError('알 수 없는 템플릿 작업입니다')
