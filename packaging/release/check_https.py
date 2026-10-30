"""배포 FFmpeg로 인증서를 검증하며 실제 HTTPS 구간을 수신·디코딩한다."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT/'tests/fixtures/https-media.mp4'
DIGEST = '064e914cf3ac2c20cc1df6761abc348cecdf7cf898c0a3e68373624e76eef653'
FIXTURES = {
    'https-media.mp4': DIGEST,
    'https-master.m3u8': '6bcce75c2bbe6bcf82c8f835f6f5dc4a1b792e5a0b68553e734ced27465d4c9e',
    'https-media.m3u8': 'ed7a9e5fb71c28f0733657513c879292740d3c6f18c9ab6afc0690499954461e',
    'https-segment.ts': 'f07419d4427ec4927855a6caefbf3a0628cdda746d31794b30abb5790db89010',
    'https-fmp4-init.mp4': 'a34730609e59f11847fd298b6a4255dda534318fd1b3928de3f8bd250be0d2af',
    'https-fmp4-00.m4v': '073ae0a2a4c6c469d990e20ed5d721fd56de797fb70ad880a522503448b448a3',
    'https-fmp4-01.m4v': 'b10e4b64e8d66058e43964d86e45f7957cd12659b0407f5274ec8d59c72dd590',
    'https-fmp4-00.m4s': '073ae0a2a4c6c469d990e20ed5d721fd56de797fb70ad880a522503448b448a3',
    'https-fmp4-01.m4s': 'b10e4b64e8d66058e43964d86e45f7957cd12659b0407f5274ec8d59c72dd590',
    'https-fmp4-m4v.m3u8': '76725e9617380b1e16e1f361b503a970a8c1cc245cddf02bf5ba155a435aeea3',
    'https-fmp4-m4s.m3u8': 'fb8261d86d4c89b7a4381c46d4c83c3e17987f8062430ffdefda77dd38243a94',
    'https-fmp4-query.m3u8': '418246d03e14a0c3f093453aab4c960492db8d4c3ed925626e0b85c6d9f550be',
}
RANGES = {'mp4': 'https-media.mp4', 'hls': 'https-master.m3u8',
          'hls_fmp4_m4v': 'https-fmp4-m4v.m3u8', 'hls_fmp4_m4s': 'https-fmp4-m4s.m3u8',
          'hls_fmp4_query': 'https-fmp4-query.m3u8?fixture=1'}


@contextmanager
def exact_tools(tools):
    """PATH에 의존하지 않고 실제 자식 프로세스의 실행 파일만 고정한다."""
    real_popen = subprocess.Popen
    paths = dict(zip(('ffmpeg', 'ffprobe'), tools))
    calls = []

    def launch(args, *positional, **kwargs):
        if isinstance(args, (list, tuple)) and args:
            tool = Path(str(args[0])).stem.lower()
            if tool in paths:
                args = [str(paths[tool]), *args[1:]]
                calls.append(tool)
        return real_popen(args, *positional, **kwargs)

    with patch.object(subprocess, 'Popen', side_effect=launch):
        yield calls


def check(ffmpeg, ffprobe, repository, revision):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('검사 저장소 이름이 올바르지 않습니다')
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('HTTPS 검사에는 공개된 커밋의 40자리 SHA가 필요합니다')
    for name, digest in FIXTURES.items():
        if hashlib.sha256((FIXTURE.parent/name).read_bytes()).hexdigest() != digest:
            raise ValueError('합성 검사 자료의 원본 해시가 다릅니다: '+name)
    tools = [Path(ffmpeg).resolve(), Path(ffprobe).resolve()]
    if any(not tool.is_file() for tool in tools) or tools[0].parent != tools[1].parent:
        raise ValueError('같은 배포 폴더의 FFmpeg·ffprobe 실행 파일을 지정하세요')
    protocols = subprocess.check_output([str(tools[0]), '-hide_banner', '-protocols'], timeout=15).decode('utf-8', errors='replace').split()
    if not {'https', 'tls', 'tcp', 'file'}.issubset(protocols):
        raise ValueError('배포 FFmpeg에 HTTPS/TLS 지원이 없습니다')
    base = f'https://raw.githubusercontent.com/{repository}/{revision}/tests/fixtures'
    # Python과 FFmpeg가 같은 커밋의 작은 합성 자료를 받는지 확인한다.
    for name, digest in FIXTURES.items():
        with urlopen(base+'/'+name, timeout=30) as response:
            data = response.read(100000)
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('HTTPS 검사 자료 응답의 해시가 다릅니다: '+name)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from archive import remote_media
    from archive.storage import ProjectLock
    from check_tls_rejection import check as check_rejection
    from check_hls_compat import check as check_hls

    with tempfile.TemporaryDirectory(prefix='chida-https-') as temp, exact_tools(tools) as calls:
        folder = Path(temp).resolve()
        ranges = {}
        for kind, name in RANGES.items():
            output = folder/(kind+'-range.mp4')
            # 치지직의 주소 조회만 대체하고 앱의 실제 HTTPS 수신·검사 코드를 실행한다.
            with patch.object(remote_media, 'YoutubeDL') as downloader, ProjectLock(folder) as lock:
                downloader.return_value.__enter__.return_value.extract_info.return_value = {'url': base+'/'+name}
                result = remote_media.receive('1', 1000, 3000, output, threading.Event(), lock, lambda **v: None)
            if abs(result['duration']-2) > .15 or result['bytes'] <= 0:
                raise ValueError('HTTPS 구간 수신의 출력 길이·크기가 잘못됐습니다: '+kind)
            ranges[kind] = {'duration_seconds': result['duration'], 'output_bytes': result['bytes'],
                            'full_decode_passed': True}
        if calls.count('ffmpeg') != 2*len(RANGES) or calls.count('ffprobe') != len(RANGES):
            raise ValueError('구간 수신·디코딩·검사가 지정된 실행 도구로 진행되지 않았습니다')
        rejected = check_rejection(tools[0], folder, FIXTURE.parent, ROOT/'build/test-deps')
        hls_rejected = check_hls(tools[0], folder/'hls-invalid', FIXTURE.parent)
        return {'source_revision': revision, 'fixture_sha256': DIGEST,
                'fixture_hashes': FIXTURES, 'https_and_tls_protocols': True, 'tls_verify': True,
                'range_start_seconds': 1, 'range_end_seconds': 3, 'ranges': ranges,
                'untrusted_certificate_rejected': rejected,
                'hls_format_guards': hls_rejected,
                'tools': {name: {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                          for name, path in zip(('ffmpeg', 'ffprobe'), tools)},
                'executions': {name: calls.count(name) for name in ('ffmpeg', 'ffprobe')}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    suffix = '.exe' if os.name == 'nt' else ''
    parser.add_argument('--ffmpeg', default=str(ROOT/'build/native/ffmpeg'/('ffmpeg'+suffix)))
    parser.add_argument('--ffprobe', default=str(ROOT/'build/native/ffmpeg'/('ffprobe'+suffix)))
    parser.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY', 'redpanya/Chi_Da_analyzer'))
    parser.add_argument('--revision', default=os.environ.get('GITHUB_SHA', ''))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = check(args.ffmpeg, args.ffprobe, args.repository, args.revision)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text+'\n', encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
