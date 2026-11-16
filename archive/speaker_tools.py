"""선택한 모델 폴더에서 현재 플랫폼용 화자 실행 도구를 선택한다."""
import platform
import re
import sys
import time

from . import model_paths, speaker_tool_integrity as integrity
from .storage import read_json

PROTOCOL = 1
RELEASE = 'speaker-tools-v1'
REPOSITORY = 'redpanya/Chi_Da_analyzer'
ENTRIES = {'sherpa': 'sherpa-worker', 'pyannote': 'pyannote-worker', 'fluid': 'archive-fluid-diarizer'}


def platform_id():
    machine = platform.machine().lower()
    if sys.platform == 'darwin' and machine == 'arm64': return 'macOS-arm64'
    if sys.platform == 'win32' and machine in ('amd64', 'x86_64'): return 'Windows-x64'
    return None


def supported(backend):
    if backend not in ENTRIES: raise ValueError('지원하는 화자 엔진을 선택하세요')
    return platform_id() in (('macOS-arm64',) if backend == 'fluid' else ('macOS-arm64', 'Windows-x64'))


def home(backend):
    if backend not in ENTRIES: raise ValueError('지원하는 화자 엔진을 선택하세요')
    return model_paths.root()/'speaker-tools'/(platform_id() or 'unsupported')/backend


def entry_name(backend):
    return ENTRIES[backend]+('.exe' if sys.platform == 'win32' else '')


def managed(backend, *, root=None):
    root = home(backend) if root is None else root
    try:
        if not supported(backend): return None
        integrity.safe_path(root/'active.json')
        active = read_json(root/'active.json')
        if not isinstance(active, dict): return None
        if active.get('release') != RELEASE or active.get('sha256') != integrity.PINS[platform_id(), backend][0]:
            return None
        version = active['version']
        if not isinstance(version, str) or not re.fullmatch(r'[0-9a-f]{32}', version): return None
        folder = root/'versions'/version
        integrity.safe_path(folder/'tool.json')
        manifest = read_json(folder/'tool.json')
        if not isinstance(manifest, dict): return None
        if (manifest.get('backend'), manifest.get('protocol'), manifest.get('platform'), manifest.get('entry')) != (
                backend, PROTOCOL, platform_id(), entry_name(backend)): return None
        file = folder/entry_name(backend)
        integrity.plain(file)
        return file if file.is_file() else None
    except (OSError, ValueError, KeyError, TypeError): return None


def status(backend):
    file = managed(backend)
    return {'ready': bool(file), 'source': 'installed' if file else 'missing', 'path': str(file) if file else '',
            'install_path': str(home(backend)), 'supported': supported(backend), 'managed': bool(file), 'release': RELEASE}


def command(backend, request=None, *, candidate=False, check=False, executable=None):
    file = executable or managed(backend)
    if not file: raise ValueError('모델 폴더의 실행 도구를 먼저 설치하세요')
    args = [str(file)]
    if check: return args + ['--speaker-tool-check']
    if backend == 'sherpa': args += ['--voice-candidate-worker' if candidate else '--voice-worker']
    return args + [str(request)]


def check(args, log, stop, lock, backend):
    from . import speech_media
    began = time.monotonic()
    def poll():
        if time.monotonic()-began > 120: raise ValueError('실행 도구 검사가 2분을 넘었습니다. 다시 설치하거나 실행 로그를 확인하세요')
    speech_media.process(args, log, stop, lock, on_poll=poll)
    marker = f'CHIDA_SPEAKER_TOOL:{PROTOCOL}:{backend}'
    if marker not in log.read_text(encoding='utf-8', errors='replace').splitlines():
        raise ValueError('실행 도구 응답이 현재 앱과 호환되지 않습니다. 별도 실행 도구를 설치하세요')
