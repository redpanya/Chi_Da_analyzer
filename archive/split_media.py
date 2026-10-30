"""MP4의 키프레임 계획·트랙 검사. 인코더를 사용하지 않는다."""
from fractions import Fraction
import json
import subprocess
import time
from . import processes, split_contract as contract
from .source import check_cancel


def capture(args, stop, *, timeout=45, lock_fd=None):
    child = processes.popen(args, lock_fd=lock_fd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    started = time.monotonic()
    try:
        while True:
            check_cancel(stop)
            if time.monotonic() - started > timeout:
                raise ValueError('파일 검사 시간이 초과됐습니다. 디스크 연결과 파일 상태를 확인하세요')
            try:
                stdout, stderr = child.communicate(timeout=.2)
                break
            except subprocess.TimeoutExpired:
                continue
        if child.returncode:
            raise ValueError('영상 도구 오류: ' + stderr.decode('utf-8', errors='replace')[-1800:])
        return stdout
    finally:
        if child.poll() is None:
            processes.stop(child)


def input_args(path):
    # MOV의 외부 파일 참조와 네트워크 프로토콜을 허용하지 않는다.
    return ['-protocol_whitelist', 'file', '-enable_drefs', '0', '-use_absolute_path', '0', '-f', 'mov', '-i', str(path)]


def probe(path, stop):
    return json.loads(capture(['ffprobe', '-v', 'error', *input_args(path),
                              '-show_streams', '-show_format', '-show_chapters', '-of', 'json'], stop))


def inspect(value, stop):
    path = contract.local_path(value)
    if path.suffix.lower() != '.mp4':
        raise ValueError('현재 영상 나누기는 MP4 · H.264/AAC를 지원합니다')
    mark = contract.identity(path)
    data = probe(path, stop)
    streams = data.get('streams', [])
    video = [s for s in streams if s.get('codec_type') == 'video']
    if len(video) != 1 or video[0].get('codec_name') != 'h264' or video[0].get('disposition', {}).get('attached_pic'):
        raise ValueError('H.264 영상 트랙이 하나인 MP4를 선택하세요')
    if any(s.get('codec_type') not in ('video', 'audio') or
           (s['codec_type'] == 'audio' and s.get('codec_name') != 'aac') for s in streams):
        raise ValueError('지원하지 않는 트랙이 있습니다. 트랙을 버리지 않기 위해 분할을 시작하지 않습니다')
    if data.get('chapters'):
        raise ValueError('챕터가 있는 MP4는 아직 지원하지 않습니다. 원본은 변경하지 않았습니다')
    v = video[0]
    try:
        duration = float(data['format']['duration'])
        origin = float(data['format'].get('start_time', 0))
        fps = float(Fraction(v['avg_frame_rate']))
        if not 0 < fps <= 240 or abs(fps-float(Fraction(v['r_frame_rate']))) > .01:
            raise ValueError()
        if not 0 < duration <= 7*86400:
            raise ValueError()
    except (KeyError, ValueError, ZeroDivisionError):
        raise ValueError('영상 길이·일정한 프레임률을 확인할 수 없습니다. 이 형식은 아직 지원하지 않습니다') from None
    source = {'path': str(path), 'name': path.name, 'identity': mark, 'duration': duration,
              'origin': origin, 'fps': fps, 'width': v['width'], 'height': v['height'],
              'video_index': v['index'], 'streams': streams, 'audio_count': len(streams)-1}
    contract.unchanged(source)
    return source


def boundaries(source, requested, stop, update):
    path = contract.unchanged(source)
    cuts = []
    for index, at in enumerate(requested):
        check_cancel(stop)
        candidate = None
        # 주변 탐색만 수행한다. 긴 GOP는 최대 5분까지 확장하고 자동 인코딩하지 않는다.
        for span in (5, 30, 300):
            start = max(0, at + source['origin'] - 2)
            end = min(source['origin'] + source['duration'], at + source['origin'] + span)
            data = json.loads(capture(['ffprobe', '-v', 'error', *input_args(path),
                '-read_intervals', f'{start:.6f}%{end:.6f}', '-select_streams', 'v:0',
                '-show_packets', '-show_entries', 'packet=pts_time,flags', '-of', 'json'], stop))
            times = [float(r['pts_time'])-source['origin'] for r in data.get('packets', [])
                     if 'K' in r.get('flags', '') and 'pts_time' in r]
            candidate = next((v for v in sorted(times) if v >= at-.000001), None)
            if candidate is not None:
                break
        if candidate is None or candidate >= source['duration']-1/source['fps']:
            raise ValueError(f'{at:.3f}초 이후에 사용할 분할 경계가 없습니다. 앞쪽 시각을 선택하세요')
        if cuts and candidate <= cuts[-1]['actual']+.000001:
            raise ValueError('여러 분할점이 같은 키프레임에 겹칩니다. 가까운 분할점을 하나로 줄이세요')
        cuts.append({'requested': at, 'actual': candidate, 'difference': candidate-at})
        update(progress=(index+1)/len(requested), message=f'분할 경계 확인 {index+1}/{len(requested)}')
    contract.unchanged(source)
    edges = [0, *[c['actual'] for c in cuts], source['duration']]
    parts = [{'index': i, 'start': a, 'end': b, 'duration': b-a,
              'name': f'{contract.safe_stem(source["name"])}_part-{i+1:03d}.mp4'}
             for i, (a, b) in enumerate(zip(edges, edges[1:]))]
    return {'cuts': cuts, 'parts': parts}


def stream_signature(stream):
    keys = ('codec_type', 'codec_name', 'profile', 'width', 'height', 'pix_fmt',
            'sample_rate', 'channels', 'channel_layout', 'sample_aspect_ratio',
            'color_range', 'color_space', 'color_transfer', 'color_primaries')
    result = {k: stream.get(k) for k in keys}
    result['tags'] = {k: stream.get('tags', {}).get(k) for k in ('language', 'handler_name')}
    result['default'] = stream.get('disposition', {}).get('default', 0)
    result['rotation'] = [s.get('rotation') for s in stream.get('side_data_list', []) if 'rotation' in s]
    return result


def verify(path, source, part, stop, audio_selection=None):
    from .split_audio import streams as selected_streams
    data = probe(path, stop)
    streams = data.get('streams', [])
    expected_streams = selected_streams(source, audio_selection)
    if [stream_signature(s) for s in streams] != [stream_signature(s) for s in expected_streams]:
        raise ValueError('출력 트랙·오디오·메타데이터가 유지할 원본 트랙과 다릅니다. 원본은 보존했습니다')
    v = next(s for s in streams if s['codec_type'] == 'video')
    duration = float(v.get('duration', 0))
    src_video = next(s for s in source['streams'] if s['codec_type'] == 'video')
    video_end = float(src_video.get('start_time', 0)) + float(src_video.get('duration', source['duration'])) - source['origin']
    expected = min(part['end'], video_end) - max(part['start'], float(src_video.get('start_time', 0))-source['origin'])
    if abs(duration-expected) > max(.025, 1.1/source['fps']):
        raise ValueError('출력 영상 범위가 계획과 다릅니다. 미완성 파일은 완료 처리하지 않습니다')
    if abs(float(v.get('start_time', 0))) > .1:
        raise ValueError('출력 시작 시간축을 확인할 수 없습니다')
    for start in (0, max(0, duration-2)):
        capture(['ffmpeg', '-v', 'error', '-nostdin', '-xerror', '-ss', str(start),
                 *input_args(path), '-t', '2', '-map', '0', '-f', 'null', '-'], stop, timeout=60)
    return {'duration': duration, 'bytes': path.stat().st_size,
            'streams': len(streams), 'audio_tracks': len(streams)-1,
            'source_stream_indices': [s['index'] for s in expected_streams],
            'check': '선택 트랙·길이·시작/끝 디코딩 검사'}
