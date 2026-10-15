"""영상 재생 시각을 유지하는 음성 파생 파일과 중단 가능한 자식 프로세스."""

from array import array
import math
import shutil
import subprocess
from . import processes
import sys
import uuid
import wave

from . import audio_limits
from .source import Cancelled, check_cancel
from .storage import asset_path, Conflict
from .video import probe
from .speech_model import digest

RATE = 16000


def local(path, relative):
    target = path / 'speech' / relative
    if not target.resolve().is_relative_to((path / 'speech').resolve()):
        raise ValueError('음성 자료 경로가 올바르지 않습니다')
    for parent in [target, *target.parents]:
        if parent == path:
            break
        if parent.is_symlink():
            raise Conflict('음성 자료의 연결 파일은 지원하지 않습니다')
    return target


def identity(file, path):
    stat = file.stat()
    return {'file': str(file.relative_to(path)), 'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns}


def source(path, data):
    if data['tasks']['video']['state'] != 'complete':
        raise ValueError('영상 다운로드와 검사를 먼저 완료하세요')
    return asset_path(path, data['tasks']['video']['assets']['playback'])


def info(path, data):
    file = source(path, data)
    value = probe(file)
    duration = float(value['format']['duration'])
    origin = float(value['format'].get('start_time', 0))
    if not math.isfinite(duration) or not 0 < duration <= 7 * 86400 or not math.isfinite(origin):
        raise ValueError('지원하는 영상 길이 범위를 벗어났습니다')
    audio_limits.duration(round(duration * 1000))
    tracks = [{'index': s['index'], 'codec': s.get('codec_name'), 'channels': s.get('channels'),
               'language': s.get('tags', {}).get('language', '미지정'),
               'title': s.get('tags', {}).get('title', ''), 'start_seconds': float(s.get('start_time', origin)) - origin}
              for s in value['streams'] if s['codec_type'] == 'audio']
    return {'source': identity(file, path), 'duration_ms': round(duration * 1000),
            'origin_seconds': origin, 'tracks': tracks, 'estimated_bytes': math.ceil(duration * RATE) * 2 + 44}


def process(args, log, stop, lock, on_poll=None):
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('wb') as output:
        child = processes.popen(args, stdout=output, stderr=subprocess.STDOUT, lock_fd=lock.fd)
        try:
            while child.poll() is None:
                if on_poll:on_poll()
                if stop.wait(.2):
                    raise Cancelled()
            check_cancel(stop)
            if child.returncode:
                raise ValueError(f'음성 처리 프로그램이 종료됐습니다({child.returncode}). 메모리·디스크와 {log.name}을 확인하세요')
        finally:
            processes.stop(child, timeout=5)


def validate_wav(file, duration_ms, stop=None):
    with wave.open(str(file), 'rb') as audio:
        if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (RATE, 1, 2):
            raise ValueError('추출 WAV 형식이 올바르지 않습니다')
        frames = audio.getnframes()
        if abs(frames / RATE * 1000 - duration_ms) > 1:
            raise ValueError('추출 음성과 영상의 길이가 일치하지 않습니다')
        total = 0
        while block := audio.readframes(RATE * 30):
            if stop is not None:check_cancel(stop)
            total += len(block) // 2
        if total != frames:
            raise ValueError('추출 음성 파일이 잘렸습니다')


def extract(path, data, track, stop, lock, update):
    details = info(path, data)
    if type(track) is not int or track not in {t['index'] for t in details['tracks']}:
        raise ValueError('사용할 수 있는 오디오 트랙을 선택하세요. 오디오 없는 영상은 추출할 수 없습니다')
    if shutil.disk_usage(path).free < details['estimated_bytes'] + 128 * 1024**2:
        raise OSError(28, '오디오 저장 공간 부족')
    relative = f'audio-{uuid.uuid4().hex}/source.wav'
    final = local(path, relative)
    final.parent.mkdir(parents=True)
    part = final.with_name('source.part.wav')
    frames = round(details['duration_ms'] * RATE / 1000)
    update(message='선택한 트랙을 추출하고 있습니다. 원본 시간과 무음을 유지합니다', progress={})
    process(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-copyts', '-i', str(source(path, data)),
             '-map', f'0:{track}', '-vn', '-af',
             f"asetpts=PTS-({details['origin_seconds']})/TB,aresample={RATE}:async=1:first_pts=0,apad,atrim=end_sample={frames}",
             '-ac', '1', '-ar', str(RATE), '-c:a', 'pcm_s16le', str(part)],
            final.parent / 'extract.log', stop, lock)
    validate_wav(part, details['duration_ms'],stop)
    if details['source'] != identity(source(path, data), path):
        raise ValueError('추출 중 영상 파일이 변경됐습니다. 다시 확인하세요')
    check_cancel(stop)
    sha = digest(part,stop)
    part.replace(final)
    return details | {'file': relative, 'track': track, 'sha256': sha}


def chunk_audio(audio, target, start_ms, end_ms):
    start, count = start_ms * RATE // 1000, (end_ms - start_ms) * RATE // 1000
    peak, square, seen = 0, 0, 0
    with wave.open(str(audio), 'rb') as source_wav, wave.open(str(target), 'wb') as output:
        output.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
        source_wav.setpos(start)
        while count:
            block = source_wav.readframes(min(count, RATE * 10))
            if not block:
                raise ValueError('전사할 오디오 조각이 잘렸습니다')
            output.writeframesraw(block)
            samples = array('h', block)
            if sys.byteorder != 'little':
                samples.byteswap()
            peak = max(peak, max(abs(v) for v in samples))
            square += sum(v * v for v in samples)
            seen += len(samples)
            count -= len(samples)
    rms = math.sqrt(square / max(1, seen))
    return {'peak': peak, 'rms': round(rms, 4), 'digital_silence': peak <= 3 and rms <= 1}
