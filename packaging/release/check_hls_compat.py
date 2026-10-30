"""MP4 별칭 보완 후에도 HLS 형식·확장자 검사가 유지되는지 검사한다."""
from pathlib import Path
import subprocess


def playlist(path, segment, init=None):
    lines = ['#EXTM3U', '#EXT-X-VERSION:7', '#EXT-X-TARGETDURATION:5']
    if init:
        lines.append(f'#EXT-X-MAP:URI="{init.name}"')
    lines += ['#EXTINF:4.0,', segment.name, '#EXT-X-ENDLIST']
    path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return path


def check(ffmpeg, folder, fixture_dir):
    folder.mkdir(parents=True, exist_ok=True)
    # 동일 합성 영상에서 형식만 다르게 만들어 도메인·VOD와 무관하게 검사한다.
    aac = folder/'aac-content.m4v'
    generated = subprocess.run([str(ffmpeg), '-hide_banner', '-nostdin', '-v', 'error',
        '-i', str(fixture_dir/'https-media.mp4'), '-map', '0:a:0', '-c:a', 'copy',
        '-f', 'adts', str(aac)], capture_output=True, timeout=30)
    if generated.returncode or not aac.is_file():
        raise ValueError('HLS AAC 대조 자료 생성 실패')
    ts = folder/'mpegts-content.m4v'
    ts.write_bytes((fixture_dir/'https-segment.ts').read_bytes())
    wrong_extension = folder/'mp4-content.png'
    wrong_extension.write_bytes((fixture_dir/'https-fmp4-00.m4v').read_bytes())
    init = folder/'init.mp4'
    init.write_bytes((fixture_dir/'https-fmp4-init.mp4').read_bytes())
    cases = [
        ('aac_m4v_rejected', playlist(folder/'aac.m3u8', aac), 'mismatches allowed extensions'),
        ('mpegts_m4v_rejected', playlist(folder/'mpegts.m3u8', ts), 'mismatches allowed extensions'),
        ('unlisted_extension_rejected', playlist(folder/'unlisted.m3u8', wrong_extension, init),
         'not in allowed_segment_extensions'),
    ]
    results = {}
    for name, source, expected in cases:
        # extension_picky/allowed_* 옵션을 바꾸지 않는다. 안전 기본값을 검사한다.
        completed = subprocess.run([str(ffmpeg), '-hide_banner', '-nostdin', '-v', 'error',
            '-protocol_whitelist', 'file,crypto', '-i', str(source), '-t', '.1', '-f', 'null', '-'],
            capture_output=True, timeout=30)
        log = completed.stderr.decode('utf-8', errors='replace').lower()
        if completed.returncode == 0 or expected not in log:
            raise ValueError(f'HLS 형식·확장자 거부 검사 실패 ({name}): '+log[-1200:])
        results[name] = True
    return results
