"""화자 실행 도구 선택. 사용자 모델 폴더와 앱 번들은 변경하지 않는다."""
from pathlib import Path
import platform
import re
import sys
import time

from . import runtime
from .storage import read_json

PROTOCOL = 1
RELEASE = 'speaker-tools-v1'
REPOSITORY = 'redpanya/Chi_Da_analyzer'
ROOT = Path(__file__).resolve().parents[1]
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
    return runtime.SUPPORT/'speaker-tools'/backend


def entry_name(backend):
    return ENTRIES[backend]+('.exe' if sys.platform == 'win32' else '')


def managed(backend):
    root = home(backend)
    try:
        active = read_json(root/'active.json')
        version = active['version']
        if not isinstance(version, str) or not re.fullmatch(r'[0-9a-f]{32}', version): return None
        folder = root/'versions'/version
        manifest = read_json(folder/'tool.json')
        if (manifest.get('backend'), manifest.get('protocol'), manifest.get('platform'), manifest.get('entry')) != (
                backend, PROTOCOL, platform_id(), entry_name(backend)): return None
        file = folder/entry_name(backend)
        if any(p.is_symlink() for p in (root.parent, root, root/'active.json', root/'versions', folder, folder/'tool.json', file)): return None
        return file if file.is_file() else None
    except (OSError, ValueError, KeyError, TypeError): return None


def resolve(backend):
    from . import voice_models
    file = managed(backend)
    if file: return file, 'installed'
    if getattr(sys, 'frozen', False):
        if backend == 'sherpa': return voice_models.PYTHON, 'bundled'
        bundle = (Path(sys.executable).parent if sys.platform == 'win32' else Path(sys._MEIPASS).parent.parent)/'diarization'
        return bundle/backend/entry_name(backend), 'bundled'
    file = {
        'sherpa': voice_models.PYTHON,
        'pyannote': ROOT/('.diarization-tools/pyannote/venv/Scripts/python.exe' if sys.platform == 'win32' else '.diarization-tools/pyannote/venv/bin/python'),
        'fluid': ROOT/'.diarization-tools/fluid/Runner/.build/release/archive-fluid-diarizer',
    }[backend]
    return file, 'development'


def status(backend):
    file, origin = resolve(backend)
    ready = file.is_file()
    return {'ready': ready, 'source': origin if ready else 'missing', 'path': str(file),
            'install_path': str(home(backend)), 'supported': supported(backend),
            'managed': bool(managed(backend)), 'release': RELEASE}


def command(backend, request=None, *, candidate=False, check=False):
    file, origin = resolve(backend)
    if not file.is_file(): raise ValueError('선택 실행 도구를 먼저 설치하세요')
    args = [str(file)]
    if backend == 'sherpa':
        if origin == 'development':
            args += [str(ROOT/'workers/sherpa_tool.py')]
        if check: args += ['--speaker-tool-check']
        else: args += ['--voice-candidate-worker' if candidate else '--voice-worker', str(request)]
    elif backend == 'pyannote':
        if origin == 'development': args += [str(ROOT/'workers/diarization_pyannote.py')]
        args += ['--speaker-tool-check'] if check else [str(request)]
    else: args += ['--speaker-tool-check'] if check else [str(request)]
    return args


def check(args, log, stop, lock, backend):
    from . import speech_media
    began = time.monotonic()
    def poll():
        if time.monotonic()-began > 120: raise ValueError('실행 도구 검사가 2분을 넘었습니다. 다시 설치하거나 실행 로그를 확인하세요')
    speech_media.process(args, log, stop, lock, on_poll=poll)
    marker = f'CHIDA_SPEAKER_TOOL:{PROTOCOL}:{backend}'
    if marker not in log.read_text(encoding='utf-8', errors='replace').splitlines():
        raise ValueError('실행 도구 응답이 현재 앱과 호환되지 않습니다. 별도 실행 도구를 설치하세요')
