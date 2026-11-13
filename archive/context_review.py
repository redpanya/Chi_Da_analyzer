"""후보 검토 표시만 별도 저장한다. 전사·요약·댓글 결과에는 쓰지 않는다."""
import re

from .context_job import local, state
from .storage import Conflict, ProjectLock, read_json, save_json, stamp

STATES = {'unreviewed', 'accepted', 'held', 'excluded'}


def target(path, run):
    if not isinstance(run, str) or not re.fullmatch(r'[a-f0-9]{32}', run):
        raise ValueError('저장된 클립 후보 버전을 선택하세요')
    saved = next((row for row in state(path)['runs'] if row['id'] == run), None)
    if not saved or saved.get('mode') != 'clips':
        raise ValueError('저장된 클립 후보 버전을 선택하세요')
    return local(path, f'reviews/{run}.json')


def read(path, run):
    file = target(path, run)
    return read_json(file) if file.exists() else {'revision': 0, 'items': {}}


def save(path, run, change):
    if (not isinstance(change, dict) or set(change) not in ({'revision', 'item', 'status'}, {'revision', 'item', 'status', 'note'})
            or type(change['revision']) is not int or change['revision'] < 0
            or not isinstance(change['item'], str) or not 0 < len(change['item']) <= 2000
            or any(ord(c) < 32 for c in change['item'])
            or not isinstance(change['status'], str) or change['status'] not in STATES):
        raise ValueError('후보 검토 항목과 상태를 확인하세요')
    if 'note' in change and (not isinstance(change['note'], str) or len(change['note']) > 1000
                             or any(ord(c) < 32 and c not in '\n\t' for c in change['note'])):
        raise ValueError('검토 메모는 1,000자 이내의 텍스트로 입력하세요')
    target(path, run)
    # 삭제·교체와 겹치면 기존 자료를 건드리지 않고 다음 저장을 요청한다.
    with ProjectLock(path):
        file = target(path, run)
        previous = read(path, run)
        if previous['revision'] != change['revision']:
            raise Conflict('다른 창에서 후보 검토를 변경했습니다. 검토 기록을 다시 불러온 뒤 변경하세요')
        items = dict(previous['items'])
        notes = dict(previous.get('notes', {}))
        if change['status'] == 'unreviewed':
            items.pop(change['item'], None)
        else:
            items[change['item']] = change['status']
        if 'note' in change:
            if change['note']:
                notes[change['item']] = change['note']
            else:
                notes.pop(change['item'], None)
        if len(set(items) | set(notes)) > 20000:
            raise ValueError('한 결과 버전에는 최대 2만 개의 검토 표시를 저장할 수 있습니다')
        result = {'revision': previous['revision'] + 1, 'items': items, 'notes': notes, 'updated_at': stamp()}
        save_json(file, result)
    return result
