"""HTTP 부분 요청을 확인한 MP4만 병렬 수신한다."""

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import hashlib
import os
import re
import shutil
import threading
import time

from yt_dlp.networking import Request
from yt_dlp.networking.exceptions import HTTPError, TransportError

from .source import Cancelled, check_cancel, fragment_concurrency
from .storage import Conflict, read_json, save_json


CHUNK_SIZE = 16 * 1024 * 1024
BUFFER_SIZE = 64 * 1024


class RangeUnsupported(ValueError):
    pass


def paths(original):
    return (original.with_name(original.name + '.part-range.json'),
            original.with_name(original.name + '.part-range.data'))


def cleanup(original):
    manifest, _ = paths(original)
    if not manifest.exists():
        return
    saved = read_json(manifest)
    if not isinstance(saved, dict) or saved.get('version') != 1 or not isinstance(saved.get('done'), dict):
        raise Conflict('식별할 수 없는 병렬 수신 기록은 정리하지 않습니다')
    for path in reversed(paths(original)):
        if path.is_symlink():
            raise Conflict('연결된 다운로드 임시 파일은 정리하지 않습니다')
        path.unlink(missing_ok=True)


def _range(response, start, end, total=None):
    value = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
    if response.status != 206 or not value:
        raise RangeUnsupported('서버가 부분 다운로드를 지원하지 않습니다')
    first, last, size = map(int, value.groups())
    length = response.headers.get('Content-Length')
    if ((first, last) != (start, end) or size <= end
            or response.headers.get('Content-Encoding', 'identity').lower() != 'identity'
            or (length is not None and length != str(end - start + 1))):
        raise RangeUnsupported('서버의 부분 응답 범위를 확인할 수 없습니다')
    if total is not None and total != size:
        raise Conflict('수신 중 원격 영상의 크기가 바뀌었습니다. 받은 자료는 보존했습니다')
    return size


def _digest(path, start, length, stop):
    value = hashlib.sha256()
    with path.open('rb') as file:
        file.seek(start)
        while length:
            check_cancel(stop)
            block = file.read(min(BUFFER_SIZE, length))
            if not block:
                return None
            value.update(block)
            length -= len(block)
    return value.hexdigest()


def _allocated(path, completed):
    if not path.exists():
        return 0
    stat = path.stat()
    if hasattr(stat, 'st_blocks'):
        return stat.st_blocks * 512
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        size = kernel.GetCompressedFileSizeW
        size.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD))
        size.restype = wintypes.DWORD
        high = wintypes.DWORD()
        ctypes.set_last_error(0)
        low = size(str(path), ctypes.byref(high))
        if low != 0xffffffff or not ctypes.get_last_error():
            return (high.value << 32) | low
    return completed


def download(downloader, info, original, stop, progress, concurrency):
    """완료하면 True, 기존 단일 수신 경로를 사용할 때는 False를 반환한다."""
    concurrency = fragment_concurrency(concurrency)
    manifest, data = paths(original)
    for path in (original, manifest, data, original.with_name(original.name + '.part')):
        if path.is_symlink():
            raise Conflict('연결된 다운로드 파일은 덮어쓰지 않습니다')
    # 이전 yt-dlp 부분 파일은 형식을 바꾸지 않고 기존 이어받기로 처리한다.
    if original.exists() or original.with_name(original.name + '.part').exists():
        return False
    if concurrency == 1 and not manifest.exists():
        return False
    headers = {k: v for k, v in info.get('http_headers', {}).items()
               if k.lower() not in ('range', 'if-range', 'accept-encoding')}
    headers['Accept-Encoding'] = 'identity'

    def request(start, end, etag=None):
        request_headers = headers | {'Range': f'bytes={start}-{end}'}
        if etag:
            request_headers['If-Range'] = etag
        try:
            return downloader.urlopen(Request(info['url'], headers=request_headers))
        except HTTPError as error:
            status = error.status
            error.close()
            if status in (400, 405, 416, 501):
                raise RangeUnsupported('서버가 부분 요청을 받지 않습니다') from None
            raise TransportError(f'HTTP {status}') from None

    check_cancel(stop)
    try:
        with request(0, 0) as response:
            total = _range(response, 0, 0)
            etag = response.headers.get('ETag', '')
            # 따옴표 없는 CDN 식별자도 그대로 비교하며 약한 식별자는 재개에 쓰지 않는다.
            if (not etag or etag.lower().startswith('w/') or len(etag) > 512
                    or any(not 33 <= ord(char) <= 126 for char in etag)):
                raise RangeUnsupported('원격 파일의 식별자를 확인할 수 없습니다')
            if len(response.read(2)) != 1:
                raise RangeUnsupported('서버의 부분 응답 길이를 확인할 수 없습니다')
    except RangeUnsupported:
        return False
    except TransportError:
        raise ValueError('MP4 부분 요청 확인에 실패했습니다. 받은 자료는 유지되며 다시 시도할 수 있습니다') from None
    if info.get('filesize') is not None and info['filesize'] != total:
        raise Conflict('영상 정보와 MP4의 실제 크기가 다릅니다. 기존 자료는 유지됩니다')

    identity = {'version': 1, 'total': total, 'etag_sha256': hashlib.sha256(etag.encode()).hexdigest(),
                'chunk_size': CHUNK_SIZE}
    count = (total + CHUNK_SIZE - 1) // CHUNK_SIZE
    if manifest.exists():
        state = read_json(manifest)
        if not isinstance(state, dict) or any(state.get(k) != v for k, v in identity.items()):
            raise Conflict('이전에 받은 MP4와 원격 파일이 달라 이어받지 않았습니다. 기존 자료는 유지됩니다')
        if not data.is_file() or data.stat().st_size != total or not isinstance(state.get('done'), dict):
            raise Conflict('병렬 수신 재개 자료를 확인할 수 없습니다. 기존 자료는 유지됩니다')
        for index, digest in state['done'].items():
            if (not index.isdigit() or str(int(index)) != index or not 0 <= int(index) < count
                    or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)):
                raise Conflict('병렬 수신 기록이 올바르지 않습니다. 기존 자료는 유지됩니다')
    else:
        if data.exists():
            raise Conflict('식별 기록이 없는 병렬 수신 파일은 덮어쓰지 않습니다')
        state = identity | {'done': {}}

    def bounds(index):
        start = index * CHUNK_SIZE
        return start, min(total, start + CHUNK_SIZE)

    # 완료 기록보다 파일 쓰기를 먼저 확정하고 재실행 시 내용도 대조한다.
    for key, digest in list(state['done'].items()):
        start, end = bounds(int(key))
        if _digest(data, start, end - start, stop) != digest:
            del state['done'][key]
    completed = sum(bounds(int(k))[1] - bounds(int(k))[0] for k in state['done'])
    # 중단된 쓰기나 Windows 선할당 공간을 다시 필요한 여유 공간으로 세지 않는다.
    remaining_space = max(0, total - _allocated(data, completed))
    if shutil.disk_usage(original.parent).free < remaining_space + 256 * 1024 * 1024:
        raise OSError(28, 'MP4의 남은 조각을 저장할 공간이 부족합니다')
    if not data.exists():
        with data.open('xb') as file:
            file.truncate(total)
    save_json(manifest, state)
    abort = threading.Event()
    lock = threading.Lock()
    inflight = {}
    started, initial = time.monotonic(), completed

    def cancelled():
        check_cancel(stop)
        if abort.is_set():
            raise Cancelled('다른 수신 작업이 종료되어 조각 수신을 정리합니다')

    def receive(index):
        start, end = bounds(index)
        for attempt in range(3):
            cancelled()
            with lock:
                inflight[index] = 0
            try:
                with request(start, end - 1, etag) as response:
                    current_tag = response.headers.get('ETag')
                    if current_tag and current_tag != etag:
                        raise Conflict('수신 중 원격 MP4가 변경됐습니다. 기존 자료는 유지됩니다')
                    _range(response, start, end - 1, total)
                    if current_tag != etag:
                        raise RangeUnsupported('부분 응답에서 원격 파일 식별자를 확인할 수 없습니다')
                    value = hashlib.sha256()
                    remaining = end - start
                    with data.open('r+b') as file:
                        file.seek(start)
                        while remaining:
                            cancelled()
                            block = response.read(min(BUFFER_SIZE, remaining))
                            if not block or len(block) > remaining:
                                raise TransportError('부분 응답이 끝나기 전에 끊겼습니다')
                            file.write(block)
                            value.update(block)
                            remaining -= len(block)
                            with lock:
                                inflight[index] = end - start - remaining
                        if response.read(1):
                            raise RangeUnsupported('부분 응답이 지정 범위를 초과했습니다')
                        file.flush()
                        os.fsync(file.fileno())
                    return value.hexdigest()
            except TransportError:
                if attempt == 2:
                    raise ValueError('MP4 조각 수신이 3회 실패했습니다. 완료한 조각은 이어받기에 사용됩니다') from None
                if abort.wait(.3 * (attempt + 1)):
                    cancelled()
        raise AssertionError('도달할 수 없는 수신 상태')

    def report(finished=False):
        with lock:
            received = completed + sum(inflight.values())
        progress({'status': 'finished' if finished else 'downloading', 'downloaded_bytes': received,
                  'total_bytes': total, 'fragment_index': len(state['done']), 'fragment_count': count,
                  'speed': max(0, received - initial) / max(.001, time.monotonic() - started),
                  'message': f'MP4 부분 다운로드 중 (동시 최대 {concurrency}개)'})

    pending = iter(i for i in range(count) if str(i) not in state['done'])
    executor = ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix='mp4-range')
    futures = {}

    def submit():
        index = next(pending, None)
        if index is not None:
            futures[executor.submit(receive, index)] = index

    try:
        for _ in range(concurrency):
            submit()
        while futures:
            cancelled()
            ready, _ = wait(futures, timeout=.2, return_when=FIRST_COMPLETED)
            for future in ready:
                index = futures.pop(future)
                digest = future.result()
                state['done'][str(index)] = digest
                save_json(manifest, state)
                start, end = bounds(index)
                with lock:
                    completed += end - start
                    inflight.pop(index, None)
                submit()
            report()
        check_cancel(stop)
    except RangeUnsupported:
        return False
    finally:
        abort.set()
        executor.shutdown(wait=True, cancel_futures=True)
    if original.exists():
        raise Conflict('이미 있는 원본을 병렬 수신 결과로 덮어쓰지 않습니다')
    data.rename(original)
    manifest.unlink()
    report(finished=True)
    return True
