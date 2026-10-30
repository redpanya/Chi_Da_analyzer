"""배포 FFmpeg로 인증서를 검증하며 실제 HTTPS 구간을 수신·디코딩한다."""
import argparse
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


def check(ffmpeg, ffprobe, repository, revision):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('검사 저장소 이름이 올바르지 않습니다')
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('HTTPS 검사에는 공개된 커밋의 40자리 SHA가 필요합니다')
    if hashlib.sha256(FIXTURE.read_bytes()).hexdigest() != DIGEST:
        raise ValueError('합성 검사 영상의 원본 해시가 다릅니다')
    tools = [Path(ffmpeg).resolve(), Path(ffprobe).resolve()]
    if any(not tool.is_file() for tool in tools) or tools[0].parent != tools[1].parent:
        raise ValueError('같은 배포 폴더의 FFmpeg·ffprobe 실행 파일을 지정하세요')
    protocols = subprocess.check_output([str(tools[0]), '-hide_banner', '-protocols'], timeout=15).decode('utf-8', errors='replace').split()
    if not {'https', 'tls', 'tcp', 'file'}.issubset(protocols):
        raise ValueError('배포 FFmpeg에 HTTPS/TLS 지원이 없습니다')
    url = f'https://raw.githubusercontent.com/{repository}/{revision}/tests/fixtures/https-media.mp4'
    # Python과 FFmpeg가 같은 커밋의 작은 합성 자료를 받는지 확인한다.
    with urlopen(url, timeout=30) as response:
        data = response.read(100000)
    if hashlib.sha256(data).hexdigest() != DIGEST:
        raise ValueError('HTTPS 검사 영상 응답의 해시가 다릅니다')

    # Windows CreateProcess도 실제 배포 도구를 찾도록 부모 환경부터 설정한다.
    previous = os.environ.get('PATH', '')
    os.environ['PATH'] = str(tools[0].parent)+os.pathsep+previous
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from archive import remote_media
    from archive.storage import ProjectLock

    try:
        with tempfile.TemporaryDirectory(prefix='chida-https-') as temp:
            folder = Path(temp).resolve()
            output = folder/'https-range.mp4'
            # 치지직의 주소 조회만 대체하고 앱의 실제 HTTPS 수신·검사 코드를 실행한다.
            with patch.object(remote_media, 'YoutubeDL') as downloader, ProjectLock(folder) as lock:
                downloader.return_value.__enter__.return_value.extract_info.return_value = {'url': url}
                result = remote_media.receive('1', 1000, 3000, output, threading.Event(), lock, lambda **v: None)
            if abs(result['duration']-2) > .15 or result['bytes'] <= 0:
                raise ValueError('HTTPS 구간 수신의 출력 길이·크기가 잘못됐습니다')
            return {'source_revision': revision, 'fixture_sha256': DIGEST,
                    'https_and_tls_protocols': True, 'tls_verify': True,
                    'range_start_seconds': 1, 'range_end_seconds': 3,
                    'duration_seconds': result['duration'], 'output_bytes': result['bytes'],
                    'full_decode_passed': True}
    finally:
        os.environ['PATH'] = previous


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
