"""로컬 영상의 키프레임 계획·트랙 검사. 인코더를 사용하지 않는다."""
from fractions import Fraction
import json
import math
import subprocess
import time
from . import processes, split_contract as contract
from .source import check_cancel
from . import split_formats as formats
from .split_formats import input_args


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


def probe(path, stop):
    return json.loads(capture(['ffprobe', '-v', 'error', *input_args(path),
                              '-show_streams', '-show_format', '-show_chapters', '-of', 'json'], stop))


def inspect(value, stop):
    path = contract.local_path(value)
    formats.output({'path': str(path)})
    mark = contract.identity(path)
    data = probe(path, stop)
    streams = data.get('streams', [])
    video = [s for s in streams if s.get('codec_type') == 'video']
    if len(video) != 1 or video[0].get('codec_name') not in formats.VIDEO_CODECS or video[0].get('disposition', {}).get('attached_pic'):
        raise ValueError('검증 가능한 영상 트랙이 하나인 파일을 선택하세요. 지원 코덱: H.264·HEVC·VP8·VP9·MPEG-4·MJPEG·ProRes')
    if any(s.get('codec_type') not in ('video', 'audio') or
           (s['codec_type'] == 'audio' and s.get('codec_name') not in formats.AUDIO_CODECS) for s in streams):
        raise ValueError('자막·데이터·첨부 또는 지원하지 않는 오디오 트랙이 있습니다. 트랙을 버리지 않기 위해 분할을 시작하지 않습니다')
    if data.get('chapters'):
        raise ValueError('챕터가 있는 영상은 아직 지원하지 않습니다. 원본은 변경하지 않았습니다')
    v = video[0]
    try:
        duration = float(data['format']['duration'])
        origin = float(data['format'].get('start_time', 0))
        fps = float(Fraction(v['avg_frame_rate']))
        if not 0 < fps <= 240 or abs(fps-float(Fraction(v['r_frame_rate']))) > .01:
            raise ValueError()
        if not 0 < duration <= 7*86400 or not math.isfinite(origin):
            raise ValueError()
    except (KeyError, ValueError, ZeroDivisionError):
        raise ValueError('영상 길이·일정한 프레임률을 확인할 수 없습니다. 이 형식은 아직 지원하지 않습니다') from None
    source = {'path': str(path), 'name': path.name, 'identity': mark, 'duration': duration,
              'origin': origin, 'fps': fps, 'width': v['width'], 'height': v['height'],
              'video_index': v['index'], 'streams': streams, 'audio_count': len(streams)-1}
    source['video_span'] = video_span(path, data, fps, stop)
    source['preview_note'] = formats.preview_note(source)
    for stream in streams:
        if stream['codec_type'] == 'audio':
            stream['preview_supported'] = stream['codec_name'] in formats.AUDIO_PREVIEWS
    contract.unchanged(source)
    return source


def video_span(path, data, fps, stop):
    """MKV/WebM의 stream.duration 생략은 처음·끝 패킷의 실제 PTS로 보완한다."""
    stream = next(s for s in data['streams'] if s['codec_type'] == 'video')
    start = float(stream.get('start_time', data['format'].get('start_time', 0)))
    duration = float(stream.get('duration', 0))
    if duration > 0 and math.isfinite(start + duration):
        return {'start': start, 'end': start + duration}
    def packets(interval):
        result = json.loads(capture(['ffprobe', '-v', 'error', *input_args(path),
            '-read_intervals', interval, '-select_streams', 'v:0', '-show_packets',
            '-show_entries', 'packet=pts_time,duration_time', '-of', 'json'], stop))
        return [p for p in result.get('packets', []) if 'pts_time' in p]
    head = packets('%+#64')
    end = float(data['format']['duration']) + float(data['format'].get('start_time', 0))
    tail = []
    for span in (10, 60, 300):
        tail = packets(f'{max(0, end-span):.6f}%')
        if tail:
            break
    if not head or not tail:
        raise ValueError('영상 처음·끝 패킷의 시간 정보를 확인하지 못했습니다')
    start = min(float(p['pts_time']) for p in head)
    end = max(float(p['pts_time']) + (float(p.get('duration_time', 0)) or 1/fps) for p in tail)
    if not math.isfinite(start + end) or end <= start:
        raise ValueError('영상 패킷의 시간 정보가 올바르지 않습니다')
    return {'start': start, 'end': end}


def independent_keyframes(packets, origin, duration, fps):
    """키프레임 뒤에 그보다 앞 시각의 프레임이 붙는 열린 GOP는 경계에서 제외한다."""
    later_min = float('inf')
    later_max = -float('inf')
    result = []
    for packet in reversed(packets):
        if 'pts_time' not in packet:
            continue
        at = float(packet['pts_time']) - origin
        # 조회 창의 마지막 키프레임은 뒤쪽 프레임까지 확인한 다음 사용한다.
        enough = later_max >= min(duration - 1/fps, at + 1) - .001
        if 'K' in packet.get('flags', '') and enough and later_min >= at - .000001:
            result.append(at)
        later_min = min(later_min, at)
        later_max = max(later_max, at)
    return sorted(result)


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
            times = independent_keyframes(data.get('packets', []), source['origin'], source['duration'], source['fps'])
            candidate = next((v for v in sorted(times) if v >= at-.000001), None)
            if candidate is not None:
                break
        if candidate is None or candidate >= source['duration']-1/source['fps']:
            raise ValueError(f'{at:.3f}초 이후에 독립 재생 가능한 분할 경계를 찾지 못했습니다. 열린 GOP 또는 긴 키프레임 간격일 수 있습니다. 다른 시각을 선택하세요. 재인코딩하거나 원본을 변경하지 않았습니다')
        if cuts and candidate <= cuts[-1]['actual']+.000001:
            raise ValueError('여러 분할점이 같은 키프레임에 겹칩니다. 가까운 분할점을 하나로 줄이세요')
        cuts.append({'requested': at, 'actual': candidate, 'difference': candidate-at})
        update(progress=(index+1)/len(requested), message=f'분할 경계 확인 {index+1}/{len(requested)}')
    contract.unchanged(source)
    edges = [0, *[c['actual'] for c in cuts], source['duration']]
    parts = [{'index': i, 'start': a, 'end': b, 'duration': b-a,
              'name': f'{contract.safe_stem(source["name"])}_part-{i+1:03d}{formats.output(source)[0]}'}
             for i, (a, b) in enumerate(zip(edges, edges[1:]))]
    return {'cuts': cuts, 'parts': parts}


def stream_signature(stream):
    keys = ('codec_type', 'codec_name', 'codec_tag_string', 'profile', 'width', 'height', 'pix_fmt',
            'sample_rate', 'channels', 'channel_layout', 'sample_aspect_ratio',
            'color_range', 'color_space', 'color_transfer', 'color_primaries')
    result = {k: stream.get(k) for k in keys}
    result['tags'] = {k: stream.get('tags', {}).get(k) for k in ('language', 'handler_name', 'title')}
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
    span = video_span(path, data, source['fps'], stop)
    duration = span['end'] - span['start']
    src_video = next(s for s in source['streams'] if s['codec_type'] == 'video')
    src_span = source.get('video_span') or {'start': float(src_video.get('start_time', 0)),
        'end': float(src_video.get('start_time', 0)) + float(src_video.get('duration', source['duration']))}
    expected = min(part['end'], src_span['end']-source['origin']) - max(part['start'], src_span['start']-source['origin'])
    if abs(duration-expected) > max(.025, 1.1/source['fps']):
        raise ValueError('출력 영상 범위가 계획과 다릅니다. 미완성 파일은 완료 처리하지 않습니다')
    if abs(span['start']) > max(.1, 1.1/source['fps']):
        raise ValueError('출력 시작 시간축을 확인할 수 없습니다')
    for start in (0, max(0, duration-2)):
        capture(['ffmpeg', '-v', 'error', '-nostdin', '-xerror', '-ss', str(start),
                 *input_args(path), '-t', '2', '-map', '0', '-f', 'null', '-'], stop, timeout=60)
    return {'duration': duration, 'bytes': path.stat().st_size,
            'streams': len(streams), 'audio_tracks': len(streams)-1,
            'source_stream_indices': [s['index'] for s in expected_streams],
            'check': '선택 트랙·길이·시작/끝 디코딩 검사'}
