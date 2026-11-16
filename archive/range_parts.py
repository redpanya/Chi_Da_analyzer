"""작업별 수신 캐시. 정상 조각은 재사용하고 네트워크 오류만 조각 단위로 재시도한다."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from hashlib import sha256
import threading
import time

from yt_dlp.networking import Request
from yt_dlp.networking.exceptions import TransportError, HTTPError
from .http_download import _range, BUFFER_SIZE
from .source import check_cancel
from .storage import Conflict


def strong_tag(value):
    return bool(value and not value.lower().startswith('w/') and len(value)<=512
                and all(33<=ord(c)<=126 for c in value))


def receive(ydl, headers, jobs, folder, count, stop, update, *, total=None, etag=None, validate_parts=False):
    guard = threading.Lock()
    abort = threading.Event()
    validate_cache = any(folder.glob('*.sha256'))
    received = active = completed = 0
    expected = sum(end-start for _,start,end,_ in jobs) if all(j[2] is not None for j in jobs) else None
    sizes = [0]*len(jobs)
    failures = []
    def check():
        check_cancel(stop)
        check_cancel(abort)

    def worker(index):
        nonlocal received, active
        url, start, end, name = jobs[index]
        target = folder/name
        digest = target.with_suffix('.sha256')
        part = target.with_suffix('.part')
        tag_file = target.with_suffix('.etag')
        cached_tag = None
        if any(p.is_symlink() for p in (target,part,digest,tag_file)):
            raise Conflict('연결된 수신 캐시는 사용할 수 없습니다')
        if validate_cache and target.is_file() and digest.is_file() and (end is None or target.stat().st_size == end-start):
            with target.open('rb') as src:
                h = sha256()
                while buf := src.read(1024**2):
                    check()
                    h.update(buf)
            if h.hexdigest() == digest.read_text('ascii'):
                if not validate_parts:
                    sizes[index] = target.stat().st_size
                    return
                tag = tag_file.read_text('ascii') if tag_file.is_file() else None
                if strong_tag(tag):
                    cached_tag = tag
        request_headers = headers.copy()
        if cached_tag:
            request_headers['If-None-Match'] = cached_tag
        if end is not None:
            request_headers['Range'] = f'bytes={start}-{end-1}'
        if etag:
            request_headers['If-Range'] = etag
        for attempt in range(3):
            check()
            reason = ''
            with guard:
                active += 1
                sizes[index] = 0
            try:
                with ydl.urlopen(Request(url,headers=request_headers)) as response:
                    if cached_tag and response.status == 304:
                        sizes[index] = target.stat().st_size
                        return
                    if etag and response.headers.get('ETag') != etag:
                        raise Conflict(f'{index+1}번째 조각 수신 중 원격 영상이 변경됐습니다')
                    if end is not None:
                        try:
                            _range(response,start,end-1,total)
                        except ValueError as error:
                            raise ValueError(f'{index+1}번째 조각 ({start}~{end-1}바이트): {error}') from None
                    elif response.status != 200:
                        raise ValueError('완전한 HLS 조각 응답을 확인할 수 없습니다')
                    length = end-start if end is not None else response.headers.get('Content-Length')
                    size = 0
                    h = sha256()
                    with part.open('wb') as dst:
                        while True:
                            check()
                            buf = response.read(BUFFER_SIZE)
                            if not buf:
                                break
                            size += len(buf)
                            if length is not None and size > int(length):
                                raise ValueError('조각의 응답 크기가 요청 범위를 초과했습니다')
                            dst.write(buf)
                            h.update(buf)
                            with guard:
                                received += len(buf)
                                sizes[index] = size
                        if not size or length is not None and size != int(length):
                            raise TransportError('조각 응답이 일찍 끝났습니다')
                    if validate_parts:
                        tag_file.unlink(missing_ok=True)
                    part.replace(target)
                    if validate_parts and strong_tag(response.headers.get('ETag')):
                        tag_file.write_text(response.headers['ETag'],encoding='ascii')
                    digest.write_text(h.hexdigest(), encoding='ascii')
                    return
            except HTTPError as error:
                reason = f'HTTP {error.status}'
                error.close()
                if error.status == 304 and cached_tag:
                    sizes[index] = target.stat().st_size
                    return
                if error.status not in (408, 425, 429) and not 500 <= error.status < 600:
                    raise ValueError(f'{index+1}번째 조각 수신 실패 ({reason})') from None
            except TransportError:
                reason = '네트워크 응답 중단'
            finally:
                with guard:
                    active -= 1
            with guard:
                failures[:] = [f'{index+1}번째 조각 {reason} ({attempt+1}/3)']
            if attempt == 2:
                raise ValueError(f'{index+1}번째 조각을 세 번 받지 못했습니다 ({reason}). 완료한 조각은 보존했습니다') from None
            stop.wait(.25*(attempt+1))

    initial = min(count,len(jobs))
    indices = iter(range(initial,len(jobs)))
    previous = time.monotonic()
    prior = rate = 0
    with ThreadPoolExecutor(max_workers=count) as pool:
        pending = {pool.submit(worker,i) for i in range(initial)}
        try:
            update(progress=0,phase='receive',message='지정 구간 조각을 받고 있습니다',connections=0,limit=count)
            while pending:
                check()
                done,pending = wait(pending,timeout=.25,return_when=FIRST_COMPLETED)
                for future in done:
                    future.result()
                    completed += 1
                    i = next(indices,None)
                    if i is not None:
                        pending.add(pool.submit(worker,i))
                now = time.monotonic()
                if now-previous < .5 and pending:
                    continue
                with guard:
                    rate = (received-prior)/max(.001, now-previous)
                    previous,prior = now,received
                    size,connections = sum(sizes),active
                    retry = failures[-1] if failures else ''
                fraction = size/expected if expected else completed/len(jobs)
                update(progress=.72*min(1,fraction),phase='receive',speed=rate,connections=connections,
                       limit=count,downloaded_bytes=size,total_bytes=expected,
                       message='지정 구간 조각 수신' + (f' / 재시도 기록: {retry}' if retry else ''))
        finally:
            abort.set()
            for future in pending:
                future.cancel()
