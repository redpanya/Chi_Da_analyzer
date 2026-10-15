"""컨테이너 표시 길이 대신 실제 패킷의 내용·상대 시간 범위를 비교한다."""
import hashlib
import json
import math
import queue
import subprocess
import threading

from . import processes
from .source import check_cancel
from .storage import read_json, save_json


def identity(file):
    stat = file.stat()
    return {'path': str(file.resolve()), 'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns}


def scan(file, info, folder, stop, lock, update):
    selected = {}
    for stream in info['streams']:
        kind = stream.get('codec_type')
        if kind in ('video', 'audio') and kind not in selected:
            selected[kind] = stream['index']
    signature = {'version': 1, 'source': identity(file), 'streams': selected}
    key = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    folder.mkdir(parents=True, exist_ok=True)
    if folder.is_symlink():
        raise ValueError('패킷 검사 폴더의 연결 파일은 사용할 수 없습니다')
    cache = folder/(key+'.json')
    if cache.is_symlink():
        raise ValueError('패킷 검사 결과의 연결 파일은 사용할 수 없습니다')
    if cache.exists():
        value = read_json(cache)
        if value.get('signature') == signature:
            return value['streams']
    stats = {index: {'count': 0, 'first': math.inf, 'end': -math.inf, 'digest': hashlib.sha256()}
             for index in selected.values()}
    pending = queue.Queue(maxsize=128)
    halt, done = threading.Event(), threading.Event()
    failures = []
    with (folder/(key+'.log')).open('wb') as log:
        child = processes.popen(['ffprobe', '-v', 'error', '-show_packets', '-show_entries',
                                 'packet=stream_index,pts_time,duration_time,size,data_hash:packet_side_data=',
                                 '-show_data_hash', 'sha256', '-of', 'compact=p=0:nk=0', str(file)],
                                stdout=subprocess.PIPE, stderr=log, lock_fd=lock.fd)
        def read():
            try:
                for line in child.stdout:
                    while not halt.is_set():
                        try:
                            pending.put(line, timeout=.1)
                            break
                        except queue.Full:
                            pass
                    if halt.is_set(): break
            except Exception as error:
                failures.append(error)
            finally:
                done.set()
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        total = 0
        try:
            while not done.is_set() or not pending.empty():
                check_cancel(stop)
                try:
                    line = pending.get(timeout=.2)
                except queue.Empty:
                    continue
                fields = dict(part.split('=', 1) for part in line.decode('ascii').strip().split('|') if '=' in part)
                if 'stream_index' not in fields: continue  # 패킷 부가 자료만 있는 줄
                index = int(fields['stream_index'])
                if index not in stats: continue
                try:
                    start, duration = float(fields['pts_time']), float(fields['duration_time'])
                    sha = fields['data_hash'].removeprefix('SHA256:')
                    if not math.isfinite(start) or not math.isfinite(duration) or duration <= 0 or len(bytes.fromhex(sha)) != 32:
                        raise ValueError()
                except (ValueError, KeyError) as error:
                    raise ValueError('패킷 시각·내용을 확인할 수 없습니다. 기존 영상은 보존했습니다') from error
                value = stats[index]
                value['count'] += 1
                value['first'] = min(value['first'], start)
                value['end'] = max(value['end'], start+duration)
                value['digest'].update((fields['size']+':'+sha+'\n').encode('ascii'))
                total += 1
                if total % 20000 == 0:
                    update(message=f'영상·음성 패킷 보존 검사 중 · {total:,}개 확인')
            child.wait(timeout=10)
            if child.returncode or failures or any(not s['count'] for s in stats.values()):
                raise ValueError('전체 패킷 검사에 실패했습니다. 기존 영상은 보존했습니다')
        finally:
            halt.set()
            processes.stop(child, timeout=5)
            reader.join(timeout=5)
            child.stdout.close()
    check_cancel(stop)
    if identity(file) != signature['source']:
        raise ValueError('검사 중 영상이 변경됐습니다. 다시 확인하세요')
    result = {kind: {k: v for k, v in stats[index].items() if k != 'digest'} |
              {'sha256': stats[index]['digest'].hexdigest()} for kind, index in selected.items()}
    save_json(cache, {'signature': signature, 'streams': result})
    return result


def compare(original, playback, *, copied):
    if set(original) != set(playback) or 'video' not in original:
        raise ValueError('재생본의 영상·음성 트랙 구성이 다릅니다. 원본은 보존했습니다')
    for value in (*original.values(), *playback.values()):
        if (not all(math.isfinite(value[key]) for key in ('first', 'end'))
                or value['end'] <= value['first'] or value['count'] <= 0):
            raise ValueError('유효한 패킷 시간 범위를 확인할 수 없습니다')
    origin = min(s['first'] for s in original.values())
    target = min(s['first'] for s in playback.values())
    differences = {}
    for kind, source in original.items():
        result = playback[kind]
        if copied and (source['count'], source['sha256']) != (result['count'], result['sha256']):
            raise ValueError('재생본의 압축 패킷 내용·개수가 다릅니다. 기존 파일은 보존했습니다')
        start_delta = (result['first']-target)-(source['first']-origin)
        end_delta = (result['end']-target)-(source['end']-origin)
        if max(abs(start_delta), abs(end_delta)) > 1:
            raise ValueError(f'재생본 {kind}의 상대 시간 범위가 다릅니다 '
                             f'(시작 {start_delta:.3f}초, 끝 {end_delta:.3f}초). 원본은 보존했습니다')
        differences[kind] = {'start_delta_seconds': start_delta, 'end_delta_seconds': end_delta}
    return {'method': 'packet-content-and-relative-span' if copied else 'packet-relative-span',
            'original_first_seconds': origin, 'playback_first_seconds': target,
            'differences': differences, 'copied': copied}
