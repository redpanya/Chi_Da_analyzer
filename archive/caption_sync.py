"""화질 교체 후 전사에 사용한 원음과 현재 재생 영상 사이의 자막 시차."""
from functools import lru_cache
from statistics import median
from threading import Event

from . import replacement_timeline, speech_media
from .storage import Conflict


def signature(file):
    stat = file.stat()
    return file, stat.st_size, stat.st_mtime_ns


@lru_cache(maxsize=64)
def _measure(wav, video, duration, track):
    try:
        offsets = replacement_timeline.measure(wav[0], video[0], duration, 5., Event(), track)
    except Conflict:
        return None
    return round(median(offsets)*1000)


def resolve(path, data, audio):
    binding = data.get('analysis_video')
    video = data['tasks']['video']
    duration = video.get('verification', {}).get('duration') if binding else None
    result = {'offset_ms': 0, 'duration_ms': round(duration*1000) if duration else None, 'message': ''}
    if not binding or not audio:
        return result
    try:
        playback = speech_media.source(path, data)
        actual = speech_media.identity(playback, path)
        if actual != binding['playback'] or audio.get('source') != binding['source']:
            raise Conflict('전사 입력 불일치')
        if audio.get('playback_source') == actual:
            return result
        # 이전 버전은 화질 교체 후 추출한 원음에도 최초 영상 ID를 기록했다.
        # 추출 날짜나 길이 차이로 방향을 추측하지 않고 해당 전사 버전의 WAV를 사용한다.
        wav = speech_media.local(path, audio['file'])
        tracks = [item['index'] for item in audio.get('tracks', [])]
        track = tracks.index(audio['track']) if tracks else 0
        duration = min(duration, audio['duration_ms']/1000)
        shift = _measure(signature(wav), signature(playback), duration, track)
        if shift is None:
            raise Conflict('음성 시차 미확인')
    except (KeyError, ValueError, OSError, TypeError):
        result['message'] = '음성 시차를 확인할 수 없어 기존 자막 시각을 사용합니다.'
        return result
    result['offset_ms'] = shift
    if shift:
        direction = '앞으로' if shift < 0 else '뒤로'
        result['message'] = f'자막 자동 보정 · {abs(shift)/1000:.2f}초 {direction}'
    else:
        result['message'] = '원음과 영상의 자막 시각이 일치합니다.'
    return result


def interval(row, sync):
    shift = sync['offset_ms']
    a, b = max(0, row['start_ms']+shift), max(0, row['end_ms']+shift)
    end = sync['duration_ms']
    return (min(a,end), min(b,end)) if end is not None else (a,b)
