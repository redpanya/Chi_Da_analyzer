"""VOD와 무관한 로컬 MP4 분할 계약. 원본 및 출력 경로를 분리한다."""
import hashlib
import math
import re
import stat
from pathlib import Path

MAX_POINTS = 200


def local_path(value, *, directory=False):
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise ValueError('로컬 파일 또는 폴더의 전체 경로를 입력하세요')
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError('전체 경로로 입력하세요')
    if path.is_symlink():
        raise ValueError('연결 파일 대신 실제 파일 경로를 선택하세요')
    path = path.resolve(strict=True)
    mode = path.stat().st_mode
    if not (stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode)):
        raise ValueError('일반 로컬 폴더 또는 파일을 선택하세요')
    return path


def identity(path):
    path = local_path(str(path))
    before = path.stat()
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        digest.update(stream.read(65536))
        stream.seek(max(0, before.st_size - 65536))
        digest.update(stream.read(65536))
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('파일이 변경 중입니다. 저장이 끝난 뒤 다시 선택하세요')
    return {'bytes': before.st_size, 'mtime_ns': before.st_mtime_ns,
            'device': before.st_dev, 'inode': before.st_ino, 'edge_sha256': digest.hexdigest()}


def unchanged(source):
    path = local_path(source['path'])
    if identity(path) != source['identity']:
        raise ValueError('원본이 변경됐거나 다른 디스크입니다. 파일을 다시 선택하세요')
    return path


def points(values, duration):
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_POINTS:
        raise ValueError(f'분할점을 1~{MAX_POINTS}개 입력하세요')
    result = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError('분할 시각은 숫자로 입력하세요')
        if not 0 < value < duration:
            raise ValueError('분할점은 영상 시작과 끝 사이에 있어야 합니다')
        result.append(round(value, 6))
    if len(set(result)) != len(result):
        raise ValueError('같은 분할 시각이 중복되었습니다')
    return sorted(result)


def safe_stem(name):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', Path(name).stem)[:60].strip(' .') or 'video'


def run_id(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{32}', value):
        raise ValueError('작업 목록에서 선택하세요')
    return value


def inside(folder, name):
    if Path(name).name != name or not name:
        raise ValueError('출력 경로가 올바르지 않습니다')
    parent = local_path(str(folder), directory=True)
    target = parent / name
    if target.is_symlink():
        raise ValueError('출력 위치에 연결 파일이 있습니다')
    return target
