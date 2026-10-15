"""요약 결과와 별도로 저장하는 댓글 초안. 버전 비교로 다른 창의 편집을 보호한다."""
import re
from .context_job import local, state
from .storage import ProjectLock, Conflict, read_json, save_json


def target(path, run):
    if not isinstance(run, str) or not re.fullmatch(r'[a-f0-9]{32}', run) or run not in [r['id'] for r in state(path)['runs']]:
        raise ValueError('저장된 문맥 버전을 선택하세요')
    return local(path, f'comments/{run}.json')


def read(path, run):
    file = target(path, run)
    return read_json(file) if file.exists() else {'revision': 0, 'text': '', 'selected': [], 'edited': False, 'basis': ''}


def save(path, run, value):
    if not isinstance(value, dict) or set(value) != {'revision','text','selected','edited','basis'}:
        raise ValueError('댓글 초안 형식을 확인하세요')
    if (type(value['revision']) is not int or value['revision'] < 0 or type(value['edited']) is not bool
            or any(not isinstance(value[k], str) or len(value[k]) > 50000 for k in ('text','basis'))
            or not isinstance(value['selected'], list) or len(value['selected']) > 5000
            or any(not isinstance(k, str) or len(k) > 500 for k in value['selected'])):
        raise ValueError('댓글은 5만 자·선택 5천 개 이내로 입력하세요')
    file = target(path, run)
    with ProjectLock(file.parent):
        previous = read(path, run)
        if previous['revision'] != value['revision']:
            raise Conflict('다른 창에서 댓글 초안을 변경했습니다. 현재 내용을 복사해 보관한 뒤 새로고침하세요')
        result = value | {'revision': previous['revision'] + 1}
        save_json(file, result)
    return result
