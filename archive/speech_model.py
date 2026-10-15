"""고정 모델의 로컬 캐시와 중단 가능한 다운로드."""

import hashlib
import shutil
import subprocess
from urllib.request import Request, urlopen

from . import model_paths
from .source import check_cancel
from .storage import ProjectLock, read_json, save_json

NAME = 'large-v3-turbo-q5_0'
SIZE = 574041195
SHA256 = '394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2'
URL = ('https://huggingface.co/ggerganov/whisper.cpp/resolve/'
       '5359861c739e955e79d9a303bcbc70fb988958b1/ggml-large-v3-turbo-q5_0.bin')


def digest(path, stop=None):
    with path.open('rb') as file:
        if stop is None:return hashlib.file_digest(file,'sha256').hexdigest()
        value=hashlib.sha256()
        check_cancel(stop)
        while block:=file.read(8*1024**2):
            check_cancel(stop);value.update(block)
        return value.hexdigest()


def model_path():
    return model_paths.root() / f'ggml-{NAME}.bin'


def status():
    cache = model_paths.root()
    path = model_path()
    ready = False
    try:
        marker = read_json(cache / 'verified.json')
        ready = (not path.is_symlink() and path.stat().st_size == SIZE
                 and marker == {'sha256': SHA256, 'mtime_ns': path.stat().st_mtime_ns})
    except (OSError, ValueError):
        pass
    return {'name': NAME, 'bytes': SIZE, 'ready': ready, 'engine': bool(shutil.which('whisper-cli')),
            'path': str(path), 'free_bytes': model_paths.free_bytes()}


def verify():
    model_paths.available()
    path = model_path()
    if path.is_symlink() or not path.is_file() or path.stat().st_size != SIZE or digest(path) != SHA256:
        raise ValueError('전사 모델이 없거나 해시가 다릅니다. 모델 준비를 다시 실행하세요')
    return path


def prepare(stop, update):
    cache = model_paths.available()
    with ProjectLock(cache):
        target = model_path()
        part = target.with_suffix('.part')
        if target.is_symlink() or part.is_symlink():
            raise ValueError('모델 캐시의 연결 파일은 지원하지 않습니다')
        if status()['ready']:
            verify()
            return
        if target.is_file() and target.stat().st_size == SIZE and digest(target) == SHA256:
            save_json(cache / 'verified.json', {'sha256': SHA256, 'mtime_ns': target.stat().st_mtime_ns})
            return
        offset = part.stat().st_size if part.exists() else 0
        if offset > SIZE:
            raise ValueError('모델 임시 파일 크기가 올바르지 않습니다. 캐시의 .part 파일을 다른 곳으로 옮기고 재시도하세요')
        if shutil.disk_usage(cache).free < SIZE - offset + 64 * 1024**2:
            raise OSError(28, '모델 저장 공간 부족')
        if offset < SIZE:
            request = Request(URL, headers={'Range': f'bytes={offset}-'} if offset else {})
            with urlopen(request, timeout=20) as response:
                if response.status == 206:
                    if not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                        raise ValueError('모델 이어받기 범위가 일치하지 않습니다')
                elif response.status == 200:
                    offset = 0
                else:
                    raise ValueError('모델 다운로드 응답을 확인할 수 없습니다')
                with part.open('ab' if offset else 'wb') as file:
                    while True:
                        check_cancel(stop)
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        file.write(block)
                        offset += len(block)
                        if offset > SIZE:
                            raise ValueError('모델 크기가 예상 범위를 벗어났습니다')
                        update(message='전사 모델을 내려받고 있습니다', progress={'bytes': offset, 'total_bytes': SIZE})
        check_cancel(stop)
        update(message='전사 모델 해시를 확인하고 있습니다')
        if part.stat().st_size != SIZE or digest(part) != SHA256:
            # 손상 자료도 보존하되 다음 준비가 같은 파일에서 재개되지 않게 한다.
            part.rename(part.with_name(part.name + '.invalid-' + str(part.stat().st_mtime_ns)))
            raise ValueError('모델 해시 검사에 실패했습니다. 다시 준비하세요')
        part.replace(target)
        save_json(cache / 'verified.json', {'sha256': SHA256, 'mtime_ns': target.stat().st_mtime_ns})


def engine_version():
    binary = shutil.which('whisper-cli')
    if not binary:
        raise ValueError('whisper-cli가 없습니다. 실행 안내의 whisper.cpp 설치 방법을 확인하세요')
    result = subprocess.run([binary, '--version'], capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise ValueError('whisper-cli를 실행할 수 없습니다')
    return binary, (result.stdout + result.stderr).strip()[:200]
