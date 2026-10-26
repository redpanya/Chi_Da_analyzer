"""요약 결과와 별도로 저장하는 댓글 초안. 버전 비교로 다른 창의 편집을 보호한다."""
import math
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


def validate_rows(value):
    if set(value) != {'revision', 'format', 'rows', 'legacy_text'} or type(value['format']) is not int or value['format'] != 2:
        raise ValueError('댓글 목록 형식을 확인하세요')
    rows = value['rows']
    if (type(value['revision']) is not int or value['revision'] < 0
            or not isinstance(rows, list) or len(rows) > 5000
            or not isinstance(value['legacy_text'], str) or len(value['legacy_text']) > 50000):
        raise ValueError('댓글은 5만 자·목록 5천 개 이내로 입력하세요')
    ids, sources, total = set(), set(), 0
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'id', 'source_id', 'start_ms', 'end_ms', 'title'}:
            raise ValueError('댓글 항목 형식을 확인하세요')
        if (not isinstance(row['id'], str) or not 0 < len(row['id']) <= 500 or row['id'] in ids
                or not isinstance(row['title'], str) or len(row['title']) > 50000
                or any(c in row['title'] for c in '\r\n')):
            raise ValueError('댓글 항목의 식별자·제목을 확인하세요')
        ids.add(row['id']); total += len(row['title'])
        source = row['source_id']
        if source is not None:
            if not isinstance(source, str) or not 0 < len(source) <= 500 or source in sources:
                raise ValueError('같은 문맥을 중복 선택할 수 없습니다')
            sources.add(source)
        start, end = row['start_ms'], row['end_ms']
        for stamp in (start, end):
            if stamp is not None and (type(stamp) not in (int, float) or not math.isfinite(stamp) or not 0 <= stamp <= 2**53-1):
                raise ValueError('댓글 항목의 시각을 확인하세요')
        if end is not None and (start is None or end <= start):
            raise ValueError('댓글 구간 끝은 시작보다 뒤여야 합니다')
    if total > 50000:
        raise ValueError('댓글 제목 합계는 5만 자 이내로 입력하세요')


def save(path, run, value):
    if not isinstance(value, dict):
        raise ValueError('댓글 초안 형식을 확인하세요')
    structured = value.get('format') == 2
    if structured:
        validate_rows(value)
    else:
        if set(value) != {'revision','text','selected','edited','basis'}:
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
            raise Conflict('다른 창에서 댓글 목록을 변경했습니다. 현재 내용을 복사해 보관한 뒤 새로고침하세요')
        if previous.get('format') == 2 and not structured:
            raise Conflict('목록형 댓글로 변경됐습니다. 최신 앱에서 다시 열어주세요')
        if structured and previous.get('format') != 2 and file.exists():
            backup = local(path, f'comments/{run}.legacy.json')
            if not backup.exists():
                save_json(backup, previous)
        result = value | {'revision': previous['revision'] + 1}
        save_json(file, result)
    return result
