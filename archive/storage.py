"""VOD 식별, 프로세스 간 쓰기 잠금과 원자적 상태 저장."""

from datetime import datetime, timezone
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from . import task_timing

ACTIVE = {'queued', 'running', 'downloading', 'verifying', 'exporting', 'stopping'}
FINISHED = {'complete', 'empty', 'unavailable'}


class Conflict(ValueError):
    pass


def stamp():
    return datetime.now(timezone.utc).isoformat()


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            json.dump(value, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        for attempt in range(9):
            try:
                os.replace(name, path)
                break
            except PermissionError as error:
                # Windows에서 상태 조회가 잠깐 파일을 열고 있으면 교체가 거부된다.
                if os.name != 'nt' or getattr(error, 'winerror', None) not in (5, 32, 33) or attempt == 8:
                    raise
                time.sleep(.025 * (attempt + 1))
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_json(path):
    if path.is_symlink():
        raise ValueError('연결 파일은 프로젝트 자료로 사용할 수 없습니다')
    return json.loads(path.read_text(encoding='utf-8'))


def vod_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]{0,17}', value):
        raise ValueError('VOD 번호가 올바르지 않습니다')
    return value


def library(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('저장할 상위 폴더를 입력하세요')
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError('저장 폴더는 절대 경로로 입력하세요')
    return path.resolve()


def project_path(root, vod):
    path = library(str(root)) / f'vod-{vod_id(vod)}'
    if path.is_symlink():
        raise Conflict('VOD 폴더가 다른 위치를 가리킵니다. 다른 저장 폴더를 선택하세요')
    return path


class ProjectLock:
    def __init__(self, path):
        self.fd = None
        self.path = path
        fd = None
        try:
            if os.name == 'nt':
                from .windows_runtime import exclusive_file, move_guard
                with move_guard(path):
                    path.mkdir(parents=True, exist_ok=True)
                    fd = exclusive_file(path / '.write.lock')
            else:
                import fcntl
                path.mkdir(parents=True, exist_ok=True)
                fd = os.open(path / '.write.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if fd is not None: os.close(fd)
            raise Conflict('다른 작업이 이 VOD 폴더를 사용 중입니다. 완료 또는 중단을 기다리세요') from None
        self.fd = fd

    @contextmanager
    def moving(self):
        if os.name != 'nt':
            yield
            return
        from .windows_runtime import exclusive_file, move_guard
        if self.fd is None: raise Conflict('잠금 없이 폴더를 이동할 수 없습니다')
        with move_guard(self.path):
            os.close(self.fd); self.fd = None
            try:
                yield
            finally:
                # 실패 시 기존 파일 잠금을 복구한 뒤 이동 보호를 해제한다.
                if self.path.exists(): self.fd = exclusive_file(self.path / '.write.lock')

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def load_project(path, vod):
    data = read_json(path / 'project.json')
    if data.get('schema') not in (1,2) or data.get('vod_id') != vod or path.name != f'vod-{vod}':
        raise Conflict('프로젝트의 VOD 식별 정보가 폴더와 일치하지 않습니다')
    if not isinstance(data.get('tasks'), dict) or set(data['tasks']) != {'video', 'chat'}:
        raise Conflict('프로젝트 작업 상태가 올바르지 않습니다')
    for name in ('media', 'chat-pages', 'exports', 'diagnostics', 'analysis'):
        if (path / name).is_symlink():
            raise Conflict('프로젝트 하위 폴더의 연결 파일은 지원하지 않습니다')
    return data


def create_or_load(path, metadata, format_id, local_input=None):
    vod = metadata['id']
    if (path / 'project.json').exists():
        data = load_project(path, vod)
        if local_input is not None and (data.get('input')!=local_input or data['tasks']['video']['state']=='complete'):
            raise Conflict('기존 영상이 있거나 다른 파일의 프로젝트입니다. 기존 자료를 열거나 별도 보관함을 사용하세요')
        if format_id != data['format_id']:
            raise Conflict('이 VOD 폴더의 화질은 이미 고정되어 있습니다. 기존 프로젝트를 열어 이어받으세요')
        return data
    # ExFAT에서는 잠금 파일 생성만으로도 macOS의 AppleDouble 보조 파일이 생긴다.
    allowed = {'.write.lock', '._.write.lock', '.DS_Store', '._.DS_Store'}
    unregistered = sorted(p.name for p in path.iterdir()
                          if p.name not in allowed or p.is_symlink() or not p.is_file())
    if unregistered:
        raise Conflict(f'VOD 폴더에 등록되지 않은 자료가 있어 시작할 수 없습니다. '
                       f'폴더: {path} / 항목: {", ".join(unregistered[:5])}. '
                       '기존 자료를 확인하거나 다른 보관함을 선택하세요')
    if local_input is None and format_id not in {item['id'] for item in metadata['formats']}:
        raise ValueError('제공 화질 목록에서 선택하세요')
    data = {'schema': 2, 'vod_id': vod, 'format_id': format_id,
            'metadata': metadata, 'created_at': stamp(), 'updated_at': stamp(),
            'tasks': {kind: {'state': 'idle', 'message': '아직 시작하지 않았습니다',
                             'progress': {}, 'assets': {}} for kind in ('video', 'chat')}}
    if local_input is not None:data.update(schema=2,input=local_input)
    save_json(path / 'project.json', data)
    return data


def asset_path(path, relative):
    target = path / relative
    if target.is_symlink() or not target.resolve().is_relative_to(path.resolve()):
        raise ValueError('프로젝트 밖 파일에는 접근할 수 없습니다')
    if not target.is_file():
        raise FileNotFoundError('결과 파일이 없습니다. 해당 작업을 다시 확인하세요')
    return target


def recover(path, data):
    changed = False
    for task in data['tasks'].values():
        if task['state'] in ACTIVE:
            task.update(task_timing.interrupted(task))
            task.update(state='paused', message='이전 실행이 중단됐습니다. 저장된 자료에서 이어받을 수 있습니다')
            changed = True
        if task['state'] in FINISHED:
            try:
                for relative in task.get('assets', {}).values():
                    asset_path(path, relative)
            except (FileNotFoundError, ValueError):
                task.update(state='error', message='결과 파일이 이동되거나 없습니다. 경로를 복구한 뒤 재시도하세요')
                changed = True
    if changed:
        data['updated_at'] = stamp()
        save_json(path / 'project.json', data)
    return data


class Project:
    def __init__(self, path, data, lock):
        self.path, self.data, self.lock = path, data, lock
        self.mutex = threading.RLock()

    def update(self, kind, **values):
        with self.mutex:
            data = self.snapshot()
            data['tasks'][kind] = task_timing.update(data['tasks'][kind], values)
            data['updated_at'] = stamp()
            save_json(self.path / 'project.json', data)
            self.data = data

    def snapshot(self):
        with self.mutex:
            return json.loads(json.dumps(self.data))


def upgrade_project(path, data):
    if data['schema'] == 1:
        import uuid
        save_json(path/'history'/('project-v1-'+uuid.uuid4().hex+'.json'), data)
        data = data | {'schema': 2}
        save_json(path/'project.json', data)
    return data
