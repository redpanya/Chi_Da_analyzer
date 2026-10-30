"""분할 오디오 선택 계약과 세션 전용 무압축 미리듣기 캐시."""
from collections import OrderedDict
from contextlib import contextmanager
import math
from pathlib import Path
import tempfile
import threading
import uuid
from . import split_contract as contract
from .source import check_cancel


def selection(source, value=None):
    if value is None:
        value = {'mode': 'all'}
    if not isinstance(value, dict) or value.get('mode') not in ('all', 'selected'):
        raise ValueError('전체 오디오 유지 또는 선택한 오디오 유지를 선택하세요')
    available = [s['index'] for s in source.get('streams', []) if s['codec_type'] == 'audio']
    if value['mode'] == 'all':
        return {'mode': 'all', 'tracks': available}
    tracks = value.get('tracks')
    if (not isinstance(tracks, list) or not tracks or
            any(type(i) is not int or i not in available for i in tracks) or len(set(tracks)) != len(tracks)):
        raise ValueError('유지할 오디오 트랙을 하나 이상 선택하세요. 원본에 있는 트랙만 선택할 수 있습니다')
    return {'mode': 'selected', 'tracks': [i for i in available if i in tracks]}


def streams(source, value=None):
    selected = selection(source, value)
    result = [s for s in source['streams'] if s['codec_type'] == 'video' or s['index'] in selected['tracks']]
    audios = [s for s in result if s['codec_type'] == 'audio']
    # 기존 기본 트랙을 제외했다면 MP4 출력의 첫 유지 오디오를 기본 재생으로 명시한다.
    if selected['mode'] == 'selected' and audios and not any(s.get('disposition', {}).get('default') for s in audios):
        result = [s | {'disposition': s.get('disposition', {}) | {'default': 1}} if s is audios[0] else s for s in result]
    return result


def mapping(source, value=None):
    args = []
    for index, stream in enumerate(streams(source, value)):
        # 기본 재생 트랙을 명시하고 그 외 원본 플래그는 보존한다.
        flags = '+'.join(k for k, v in stream.get('disposition', {}).items() if v) or '0'
        args += ['-map', f'0:{stream["index"]}', f'-disposition:{index}', flags]
    return args


class Preview:
    """현재 시각 주변 AAC만 복사한다. 원본 경로나 임의 파일을 GET에 노출하지 않는다."""
    def __init__(self):
        self.guard = threading.Lock()
        self.stop = threading.Event()
        self.temp = None
        self.cache = OrderedDict()
        self.readers = {}
        self.pending = {}

    def _cleanup(self):
        # HTTP 전송 중이거나 Windows에서 아직 열린 파일은 다음 정리 때 다시 시도한다.
        for token, file in tuple(self.pending.items()):
            if self.readers.get(token):
                continue
            try:
                file.unlink(missing_ok=True)
            except OSError:
                continue
            del self.pending[token]
        if self.stop.is_set() and not self.pending and not self.readers and self.temp:
            try:
                self.temp.cleanup()
            except OSError:
                return
            self.temp = None

    def close(self):
        self.stop.set()
        with self.guard:
            self.pending.update((item['info']['id'], item['file']) for item in self.cache.values())
            self.cache.clear()
            self._cleanup()

    def prepare(self, source_id, source, track, at):
        from . import split_media as media
        selection(source, {'mode': 'selected', 'tracks': [track]})
        if type(at) not in (int, float) or not math.isfinite(at) or not 0 <= at < source['duration']:
            raise ValueError('원본 범위 안의 미리보기 시각을 선택하세요')
        with self.guard:
            check_cancel(self.stop)
            self._cleanup()
            path = contract.unchanged(source)
            start = math.floor(at / 60) * 60
            key = (source_id, track, start)
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]['info']
            if self.temp is None:
                self.temp = tempfile.TemporaryDirectory(prefix='chida-split-audio-', ignore_cleanup_errors=True)
            token = uuid.uuid4().hex
            file = Path(self.temp.name) / (token + '.m4a')
            end = min(start + 60, source['duration'])
            try:
                media.capture(['ffmpeg', '-v', 'error', '-nostdin', '-n', '-ss', str(start),
                    *media.input_args(path), '-t', str(end-start), '-map', f'0:{track}',
                    '-c', 'copy', '-map_metadata', '-1', '-map_chapters', '-1',
                    '-movflags', '+faststart', str(file)], self.stop)
                data = media.probe(file, self.stop)
                output = data.get('streams', [])
                if len(output) != 1 or output[0].get('codec_name') != 'aac' or not output[0].get('duration'):
                    raise ValueError('이 시각에 재생할 오디오가 없습니다. 다른 시각을 선택하세요')
                contract.unchanged(source)
                check_cancel(self.stop)
            except BaseException:
                self.pending[token] = file
                self._cleanup()
                raise
            # 완성 파일만 등록한다. 이전 캐시 정리 실패는 새 미리듣기 결과를 무효화하지 않는다.
            info = {'id': token, 'start': start, 'end': end, 'track': track}
            self.cache[key] = {'file': file, 'source': source, 'info': info}
            while len(self.cache) > 8:
                _, old = self.cache.popitem(last=False)
                self.pending[old['info']['id']] = old['file']
            self._cleanup()
            return info

    def _file(self, token):
        contract.run_id(token)
        for item in self.cache.values():
            if item['info']['id'] == token:
                contract.unchanged(item['source'])
                return item['file']
        raise ValueError('미리듣기를 다시 준비하세요')

    def file(self, token):
        with self.guard:
            return self._file(token)

    @contextmanager
    def borrow(self, token):
        with self.guard:
            file = self._file(token)
            self.readers[token] = self.readers.get(token, 0) + 1
        try:
            yield file
        finally:
            with self.guard:
                self.readers[token] -= 1
                if not self.readers[token]:
                    del self.readers[token]
                self._cleanup()
