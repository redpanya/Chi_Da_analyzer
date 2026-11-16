"""중단 가능한 영상 수신과 원본을 보존하는 재생 검사."""

import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
from . import processes
import time
import uuid

from yt_dlp import YoutubeDL
from .source import Cancelled, check_cancel, metadata, ydl_options
from .storage import save_json, read_json, Conflict
from . import media_timeline, http_download
from .vod_extractor import extract_vod
from .video_quality import media_directory


def playlist(text):
    lines = text.splitlines()
    return {'durations': [float(line.split(':', 1)[1].split(',')[0]) for line in lines if line.startswith('#EXTINF:')],
            'sequence': next((line.split(':', 1)[1] for line in lines if line.startswith('#EXT-X-MEDIA-SEQUENCE:')), None),
            'end': '#EXT-X-ENDLIST' in lines}


def run_media(args, project, stop, log_name):
    log = project.path / 'diagnostics' / log_name
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('wb') as errors:
        # 부모가 강제 종료돼도 쓰는 자식이 종료될 때까지 프로젝트 잠금을 유지한다.
        process = processes.popen(args, stdout=subprocess.DEVNULL, stderr=errors,
                                   lock_fd=project.lock.fd)
        try:
            while process.poll() is None:
                if stop.wait(.2):
                    raise Cancelled()
            check_cancel(stop)
            if process.returncode:
                raise ValueError(f'영상 검사 또는 재생용 파일 생성에 실패했습니다. 원본을 보존했습니다 ({log_name})')
        finally:
            processes.stop(process, timeout=5)


def probe(path):
    # ffprobe JSON은 UTF-8이다. Windows 기본 문자셋의 읽기 스레드에서 디코딩하지 않는다.
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_format', '-show_streams',
                             '-of', 'json', str(path)], capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError('받은 영상 파일을 읽을 수 없습니다. 원본을 보존했습니다')
    try:
        info = json.loads(result.stdout)
        if (not isinstance(info, dict) or not isinstance(info.get('format'), dict)
                or not isinstance(info.get('streams'), list)
                or not all(isinstance(s, dict) for s in info['streams'])):
            raise ValueError('잘못된 영상 정보 구조')
    except (TypeError, ValueError) as error:
        raise ValueError('영상 정보(ffprobe JSON)가 비어 있거나 올바르지 않습니다. 원본을 보존했습니다') from error
    if not any(s.get('codec_type') == 'video' for s in info['streams']):
        raise ValueError('영상 트랙이 없습니다')
    try:
        duration = float(info['format'].get('duration', 0))
    except (TypeError, ValueError) as error:
        raise ValueError('영상 길이를 확인할 수 없습니다') from error
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('영상 길이를 확인할 수 없습니다')
    return info


def browser_streams(info):
    streams = [s for s in info.get('streams', []) if s.get('codec_type') in ('video', 'audio')]
    return any(s['codec_type'] == 'video' for s in streams) and all(
        s.get('codec_name') == 'aac' if s['codec_type'] == 'audio' else
        s.get('codec_name') == 'h264' and s.get('pix_fmt') in ('yuv420p', 'yuvj420p') for s in streams)


def reusable_mp4(path, info):
    try:
        start = float(info.get('format', {}).get('start_time', 0))
    except (TypeError, ValueError):
        return False
    # 로컬 서버가 바이트 범위 요청을 제공하므로 faststart가 없어도 원본을 사용할 수 있다.
    return (path.suffix.lower() == '.mp4' and 'mp4' in info.get('format', {}).get('format_name', '').split(',')
            and browser_streams(info) and math.isfinite(start) and abs(start) < .05)


def received_original(media, data):
    """수신 후 probe까지 도달한 원본만 네트워크 없이 다시 검사한다."""
    original, source, receipt = media/'original.mp4', media/'source.json', media/'probe.json'
    if not all(p.is_file() for p in (original, source, receipt)) or any(media.glob('original.mp4.part*')):
        return False
    saved, info = read_json(source), read_json(receipt)
    if saved.get('id') != data['vod_id'] or saved.get('format_id') != data['format_id']:
        raise Conflict('저장된 원본의 VOD·화질이 다릅니다. 기존 파일은 보존했습니다')
    try:
        size = original.stat().st_size
        if size <= 0 or int(info['format']['size']) != size:
            raise ValueError()
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError('수신 후 검사 기록과 원본 크기가 다릅니다. 기존 파일을 보존하고 확인하세요') from error
    if saved.get('protocol') == 'm3u8_native':
        return bool(saved.get('playlist', {}).get('end') and saved['playlist'].get('durations'))
    return saved.get('protocol') == 'https' and saved.get('filesize') in (None, size)


def validate_playback(project, original, original_info, playback, playback_info, copied, stop):
    cache = project.path/'media/packet-checks'
    def update(**values): project.update('video', **values)
    source = media_timeline.scan(original, original_info, cache, stop, project.lock, update)
    target = media_timeline.scan(playback, playback_info, cache, stop, project.lock, update)
    return media_timeline.compare(source, target, copied=copied)


def verify_decode(project, original, stop, run_id, duration, *, sample):
    command = ['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-abort_on', 'empty_output_stream']
    tracks = ['-map', '0:v:0', '-map', '0:a:0?', '-f', 'null', '-']
    if sample:
        seconds = 3
        starts = [0, (duration - seconds) / 2, duration - seconds]
        project.update('video', message='영상의 처음, 중간, 끝을 검사하고 있습니다')
        try:
            for index, start in enumerate(starts):
                check_cancel(stop)
                run_media(command + ['-ss', str(start), '-i', str(original), '-t', str(seconds)] + tracks,
                          project, stop, f'{run_id}/sample-{index + 1}.log')
            return {'decode_mode': 'sampled', 'sample_starts_seconds': starts, 'sample_seconds': seconds}
        except ValueError:
            project.update('video', message='표본 재생을 확인할 수 없어 영상 전체를 검사합니다')
    else:
        project.update('video', message='영상 전체를 검사하고 있습니다')
    check_cancel(stop)
    run_media(command + ['-i', str(original)] + tracks, project, stop, run_id+'/decode.log')
    return {'decode_mode': 'full', 'decode_exit_code': 0}


def download(project, stop):
    from . import download_scope, range_download
    if download_scope.remote(project.data):
        return range_download.download(project, stop)
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise ValueError('FFmpeg와 ffprobe 설치 경로를 확인한 뒤 다시 실행하세요')
    data = project.snapshot()
    vod, format_id = data['vod_id'], data['format_id']
    media = media_directory(project)
    media.mkdir(parents=True, exist_ok=True)
    for item in media.iterdir():
        if item.is_symlink():
            raise Conflict('영상 폴더의 연결 파일은 덮어쓰지 않습니다')
    original = media / 'original.mp4'
    selected = next(f for f in data['metadata']['formats'] if f['id'] == format_id)
    estimate = selected.get('estimated_bytes')
    concurrency = data['tasks']['video'].get('concurrent_fragments', 1)
    range_resume = http_download.paths(original)[0].is_file()
    # 병렬 MP4는 확인된 전체 크기와 완료 조각을 기준으로 수신기 안에서 공간을 검사한다.
    parallel_candidate = range_resume or (selected.get('protocol') == 'https' and concurrency > 1)
    needed = (int(estimate) if estimate and not original.is_file() and not parallel_candidate else 0) + 256 * 1024 * 1024
    if shutil.disk_usage(media).free < needed:
        raise OSError(28, '영상 원본을 저장할 공간이 부족합니다')
    project.update('video', state='running', message='영상 정보와 재개 자료를 확인하고 있습니다')
    last = 0
    transfer_total = None
    transfer_message = '영상을 받고 있습니다'

    def progress(value):
        nonlocal last, transfer_total
        check_cancel(stop)
        # 단일 수신의 finished 이벤트는 원격 크기 대신 내려받은 바이트 수를 보고한다.
        if value['status'] == 'downloading' and value.get('total_bytes'):
            transfer_total = value['total_bytes']
        if time.monotonic() - last >= .5 or value['status'] == 'finished':
            fields = {key: value.get(key) for key in ('downloaded_bytes', 'total_bytes',
                      'total_bytes_estimate', 'speed', 'fragment_index', 'fragment_count')}
            project.update('video', state='downloading', message=value.get('message', transfer_message), progress=fields)
            last = time.monotonic()

    options = ydl_options(concurrency) | {'format': format_id, 'outtmpl': str(original), 'progress_hooks': [progress]}
    offline = received_original(media, data)
    existing_original = original.is_file()
    expected_bytes = None
    expected_duration = None
    if not offline:
        with YoutubeDL(options) as downloader:
            info = extract_vod(downloader, vod)
            check_cancel(stop)
            if info.get('id') != vod or info.get('format_id') != format_id or info.get('has_drm'):
                raise Conflict('선택한 영상·화질과 현재 제공 정보가 다릅니다')
            protocol = info.get('protocol')
            if info.get('ext') != 'mp4' or protocol not in ('m3u8_native', 'https'):
                raise ValueError('현재 지원하는 MP4 전송 경로가 아닙니다')
            identity = {key: info.get(key) for key in ('id', 'format_id', 'ext', 'protocol', 'width', 'height', 'vcodec', 'acodec')}
            if protocol == 'm3u8_native':
                with downloader.urlopen(info['url']) as response:
                    identity['playlist'] = playlist(response.read().decode())
                if not identity['playlist']['end'] or not identity['playlist']['durations']:
                    raise ValueError('아직 확정되지 않은 영상 목록입니다. 나중에 다시 확인하세요')
            else:
                identity['filesize'] = info.get('filesize')
            source = media / 'source.json'
            if source.exists():
                if read_json(source) != identity:
                    raise Conflict('이전 영상·화질·조각 목록과 달라 이어받기를 중단했습니다. 원본은 유지됩니다')
            else:
                if any(media.glob('original.mp4*')):
                    raise Conflict('식별 정보가 없는 영상은 자동 인수하지 않습니다')
                save_json(source, identity)
            parallel = protocol == 'https' and http_download.download(downloader, info, original, stop, progress, concurrency)
            if not parallel:
                transfer_total = None
                check_cancel(stop)
                if parallel_candidate and not original.is_file():
                    partial = original.with_name(original.name + '.part')
                    received = partial.stat().st_size if partial.is_file() else 0
                    needed = max(0, int(estimate or 0) - received) + 256 * 1024 * 1024
                    if shutil.disk_usage(media).free < needed:
                        raise OSError(28, '단일 수신의 남은 영상을 저장할 공간이 부족합니다. 기존 자료는 유지됩니다')
                if protocol == 'https':
                    transfer_message = ('MP4 단일 수신 중' if concurrency == 1 and not range_resume else
                                        'MP4 단일 수신 중 (기존 이어받기 또는 부분 수신 미지원)')
                    project.update('video', message=transfer_message)
                downloader.process_info(info)
            check_cancel(stop)
            if not original.is_file() or original.stat().st_size == 0:
                raise ValueError('완성된 영상 파일이 없습니다')
            if protocol == 'https':
                expected_bytes = identity.get('filesize') or transfer_total
                if expected_bytes is not None and original.stat().st_size != expected_bytes:
                    raise ValueError('수신 크기와 저장된 영상 크기가 다릅니다. 원본을 보존했습니다')
                http_download.cleanup(original)
            if protocol == 'm3u8_native':
                with downloader.urlopen(info['url']) as response:
                    if playlist(response.read().decode()) != identity['playlist']:
                        raise ValueError('수신 중 영상 목록이 바뀌었습니다. 검증이 필요합니다')
            latest = metadata(vod, stop)
            if latest['duration'] != info.get('duration'):
                raise ValueError('수신 중 영상 길이가 바뀌었습니다. 검증이 필요합니다')
            expected_duration = latest['duration']
    run_id = uuid.uuid4().hex
    diagnostics = project.path/'diagnostics'/run_id
    diagnostics.mkdir(parents=True)
    save_json(diagnostics/'project-before.json', data)
    project.update('video', state='verifying', message='저장된 영상 정보를 확인하고 있습니다',
                   progress={'downloaded_bytes': original.stat().st_size, 'total_bytes': original.stat().st_size})
    original_info = probe(original)
    original_identity = media_timeline.identity(original)
    save_json(diagnostics/'original-probe.json', original_info)
    if not (media/'probe.json').exists(): save_json(media/'probe.json', original_info)
    duration = float(original_info['format']['duration'])
    compatible = reusable_mp4(original, original_info)
    sample = (compatible and not existing_original and not data.get('video_replacement') and expected_bytes is not None
              and duration >= 60 and isinstance(expected_duration, (int, float))
              and abs(duration - expected_duration) <= 2)
    decode = verify_decode(project, original, stop, run_id, duration, sample=sample)
    playback, playback_info, mode, timeline = original, original_info, 'original', None
    reused = False
    if not compatible:
        copy_streams = browser_streams(original_info)
        mode = 'remux' if copy_streams else 'transcode'
        # 이전 임시 재생본도 전체 패킷 내용이 같을 때만 재사용한다. 파일 이름은 유지한다.
        if copy_streams:
            for candidate in (media/'playback.mp4', media/'playback.tmp.mp4'):
                if not candidate.is_file(): continue
                try:
                    candidate_info = probe(candidate)
                    if not reusable_mp4(candidate, candidate_info): continue
                    timeline = validate_playback(project, original, original_info, candidate, candidate_info, True, stop)
                except ValueError as error:
                    save_json(diagnostics/(candidate.name+'.rejected.json'), {'error': str(error)})
                    continue
                playback, playback_info, reused = candidate, candidate_info, True
                break
        if not reused:
            needed = original.stat().st_size * (1 if copy_streams else 2) + 256 * 1024 * 1024
            if shutil.disk_usage(media).free < needed:
                raise OSError(28, '별도 재생용 MP4를 만들 공간이 부족합니다. 기존 파일은 유지됩니다')
            project.update('video', message='기존 파일을 유지하고 새 호환 재생용 MP4를 만들고 있습니다')
            temporary, playback = media/f'playback-{run_id}.part.mp4', media/f'playback-{run_id}.mp4'
            encoding = ['-c', 'copy'] if copy_streams else ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18',
                                                         '-pix_fmt', 'yuv420p', '-c:a', 'aac']
            run_media(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', str(original), '-map', '0:v:0',
                       '-map', '0:a:0?', *encoding, '-movflags', '+faststart', str(temporary)], project, stop, run_id+'/'+mode+'.log')
            playback_info = probe(temporary)
            timeline = validate_playback(project, original, original_info, temporary, playback_info, copy_streams, stop)
            check_cancel(stop)
            temporary.replace(playback)
    playback_identity = media_timeline.identity(playback)
    project.update('video', message='원본 파일의 해시를 계산하고 있습니다')
    digest = hashlib.sha256()
    with original.open('rb') as file:
        while chunk := file.read(4 * 1024 * 1024):
            check_cancel(stop)
            digest.update(chunk)
    if media_timeline.identity(original) != original_identity or media_timeline.identity(playback) != playback_identity:
        raise ValueError('검사 중 영상 파일이 변경됐습니다. 기존 결과를 보존하고 다시 확인하세요')
    verification = {**decode, 'original_sha256': digest.hexdigest(),
                    'files': {'original': original_identity, 'playback': playback_identity},
                    'bytes': original.stat().st_size, 'duration': float(playback_info['format']['duration']),
                    'original_start': original_info['format'].get('start_time'), 'playback_mode': mode,
                    'timeline': timeline, 'received_file_reused': offline, 'playback_file_reused': reused}
    save_json(diagnostics/'verification.json', verification)
    if not (media/'verification.json').exists(): save_json(media/'verification.json', verification)
    check_name = '빠른 검사' if decode['decode_mode'] == 'sampled' else '전체 검사'
    project.update('video', state='complete', message=f'영상 수신과 {check_name} 완료. '+
                   ('원본을 재생과 음성 추출에 함께 사용합니다' if mode == 'original' else
                    '검사한 기존 재생본을 사용합니다' if reused else '별도 재생용 MP4를 사용합니다'),
                   verification=verification, assets={'original': str(original.relative_to(project.path)), 'playback': str(playback.relative_to(project.path))})
