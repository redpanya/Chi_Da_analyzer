"""화질 교체 때 같은 재생 시각 부근의 음량 변화를 비교한다."""
from array import array
import math
import statistics
import subprocess
import sys
import time

from . import processes
from .source import check_cancel
from .storage import Conflict

RATE = 2000
HOP = 40  # 음량 표본 한 칸은 20ms
WINDOW, SEARCH = 8, 6  # 초


def envelope(file, start, seconds, stop, audio_track=0):
    check_cancel(stop)
    proc = processes.popen(['ffmpeg','-nostdin','-v','error','-ss',str(start),'-i',str(file),
        '-t',str(seconds),'-map',f'0:a:{audio_track}','-vn','-ac','1','-ar',str(RATE),'-f','s16le','pipe:1'],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    deadline = time.monotonic()+25
    try:
        while time.monotonic() < deadline:
            check_cancel(stop)
            try:
                raw, _ = proc.communicate(timeout=.3)
                break
            except subprocess.TimeoutExpired:
                continue
        else:
            return []
        if proc.returncode or len(raw) < seconds*RATE*2:
            return []
        samples = array('h')
        samples.frombytes(raw)
        if sys.byteorder != 'little':
            samples.byteswap()
        result = []
        for i in range(0, seconds*RATE, HOP):
            energy = sum(v*v for v in samples[i:i+HOP])/HOP
            result.append(math.log1p(energy))
        return result
    finally:
        processes.stop(proc)
        proc.stdout.close()


def offset(old, new, search=SEARCH):
    n = len(old)
    if not n or len(new) < n:
        return None
    avg = statistics.mean(old)
    centered = [v-avg for v in old]
    power = sum(v*v for v in centered)
    if power < n*.04:
        return None
    scores = []
    for i in range(len(new)-n+1):
        sample = new[i:i+n]
        variance = sum(v*v for v in sample)-sum(sample)**2/n
        scores.append(sum(x*y for x,y in zip(centered,sample))/math.sqrt(power*variance) if variance > n*.04 else 0.)
    peak = max(scores)
    index = scores.index(peak)
    # 반복 음악·일정한 소음 등 여러 시각이 비슷하게 맞으면 판정하지 않는다.
    if peak < .78 or any(s >= peak-.08 for i,s in enumerate(scores) if abs(i-index)>10):
        return None
    return round(index*HOP/RATE-search, 3)


def measure(old_file, new_file, duration, limit, stop, audio_track=0):
    # 짧은 구간에서도 세 표본은 서로 겹치지 않아야 한다.
    window = min(WINDOW, int(duration // 6))
    search = min(SEARCH, int(duration // 8))
    if window < 1 or search < 1:
        raise Conflict('시각을 비교할 음성 구간이 짧습니다')
    first = min(30., max(search, duration * .1))
    last = min(duration-window-search, max(duration-50., duration*.8-window))
    middle = min(max(duration/2, first+window), last-window)
    starts = (first, middle, last)
    offsets = []
    for i, start in enumerate(starts):
        end = starts[i+1]-window if i<2 else duration-window-search
        for at in dict.fromkeys((start, min(start+14, max(start,end)))):
            reference = envelope(old_file, at, window, stop)
            sample = envelope(new_file, at-search, window+2*search, stop, audio_track)
            match = offset(reference, sample, search)
            if match is not None:
                offsets.append(match)
                break
        else:
            raise Conflict(f'{int(start)}초 부근의 음성 시각을 확인하지 못했습니다')
    if max(offsets)-min(offsets) > .4 or max(abs(v) for v in offsets) > limit:
        raise Conflict(f'구간별 음성 시각 차이 {offsets}초를 확인하세요')
    return offsets


def compare(old_file, new_file, old, new, baseline, stop):
    if not all(isinstance(x,(int,float)) and math.isfinite(x) and x>0 for x in (old,new,baseline)):
        raise Conflict('영상 길이를 확인할 수 없습니다. 기존 영상을 계속 사용합니다')
    delta = max(abs(new-old),abs(new-baseline))
    limit = min(5., max(2., min(old,new,baseline)*.001))
    detail = f'기존 {old:.3f}초 · 새 영상 {new:.3f}초 · 길이 차이 {abs(old-new):.3f}초'
    if delta <= 2:
        return {}
    if delta > limit:
        raise Conflict(f'{detail} · 기존 영상 또는 분석 기준과 허용 차이 {limit:.1f}초를 넘습니다. 기존 영상을 유지합니다')
    try:
        offsets = measure(old_file, new_file, min(old,new), limit, stop)
    except Conflict as error:
        raise Conflict(f'{detail} · {error}. 기존 영상을 유지합니다') from error
    return {'length_delta_seconds':round(new-old,3), 'audio_offsets_seconds':offsets,
            'new_minus_old_seconds':statistics.median(offsets)}
