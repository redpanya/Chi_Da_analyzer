"""공용 모델 폴더 선택. 기존 파일을 이동하거나 삭제하지 않는다."""
from pathlib import Path
import re
import shutil
import tempfile

from . import runtime
from .storage import library


def root():
    return runtime.MODEL_ROOT


def checked(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('모델을 저장할 폴더의 절대 경로를 입력하세요')
    given = Path(value).expanduser()
    if given.is_symlink():
        raise ValueError('모델 폴더는 연결 폴더 대신 실제 경로를 입력하세요')
    path = library(value)
    for parent in (path, *path.parents):
        if re.fullmatch(r'vod-[0-9]+', parent.name) or (parent/'project.json').is_file():
            raise ValueError('모델은 VOD 전용 폴더 밖에 저장하세요. VOD 삭제 시 함께 삭제될 수 있습니다')
    if path.parts[:2] == ('/', 'Volumes') and len(path.parts) > 2:
        if not Path(*path.parts[:3]).is_mount():
            raise ValueError('모델 저장 드라이브가 연결되지 않았습니다. 연결 후 다시 시도하세요')
    if path.exists() and not path.is_dir():
        raise ValueError('모델 경로가 파일입니다. 폴더를 선택하세요')
    if any((path/name).is_symlink() for name in ('voices', 'context', 'separation')):
        raise ValueError('모델 하위 연결 폴더는 지원하지 않습니다')
    return path


def available():
    return checked(str(root()))


def apply(value):
    path = checked(value)
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=path) as file:
            file.write(b'check'); file.flush()
    except OSError as error:
        raise ValueError('모델 폴더에 쓸 수 없습니다. 접근 권한·연결 상태·여유 공간을 확인하세요') from error
    runtime.save_settings(models=str(path))
    runtime.MODEL_ROOT = path


def free_bytes():
    path = root()
    while not path.exists() and path != path.parent:
        path = path.parent
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return 0
