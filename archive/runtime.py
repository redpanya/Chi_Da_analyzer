"""앱에 포함한 도구와 사용자 설정. 개발 실행의 환경은 변경하지 않는다."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

from .storage import ProjectLock, read_json, save_json

FROZEN = bool(getattr(sys, 'frozen', False))
SUPPORT = (Path(os.environ.get('LOCALAPPDATA', Path.home()/'AppData/Local'))/'ChiDaAnalyzer'
           if os.name == 'nt' else Path.home()/'Library/Application Support/치지직 보관함')
DEFAULT_MODELS = SUPPORT/'models' if os.name == 'nt' else Path.home()/'Library/Caches/chzzk-archive'
MODEL_ROOT = DEFAULT_MODELS


def settings():
    try:
        value = read_json(SUPPORT/'settings.json')
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(**values):
    with ProjectLock(SUPPORT):
        file = SUPPORT/'settings.json'
        current = read_json(file) if file.exists() else {}
        if not isinstance(current, dict):
            raise ValueError('앱 설정 파일을 읽지 못했습니다. 기존 설정을 확인하세요')
        save_json(file, current | values)


def configure():
    global MODEL_ROOT
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    value = settings().get('models')
    MODEL_ROOT = Path(value) if isinstance(value, str) and Path(value).is_absolute() else DEFAULT_MODELS
    if not FROZEN:
        return
    base = Path(sys._MEIPASS)
    native = base/'native'
    paths = [str(native/name) for name in ('ffmpeg', 'whisper', 'llama') if (native/name).is_dir()]
    system = ([str(Path(os.environ['SystemRoot'])/'System32'), os.environ['SystemRoot']]
              if os.name == 'nt' else ['/usr/bin', '/bin', '/usr/sbin', '/sbin'])
    os.environ['PATH'] = os.pathsep.join([*paths, str(base/'bin'), *system])
    os.environ['SSL_CERT_FILE'] = str(base/'certs/cacert.pem')
    os.environ['REQUESTS_CA_BUNDLE'] = os.environ['SSL_CERT_FILE']
    os.environ.pop('PYTHONPATH', None)
    os.environ.pop('PYTHONHOME', None)
    os.environ.pop('GGML_BACKEND_PATH', None)


def library_default():
    if FROZEN:
        value = settings().get('library')
        if isinstance(value, str) and Path(value).is_absolute():
            return Path(value)
    return Path.home() / ('Videos/ChiDaAnalyzer' if os.name == 'nt' else 'Movies/치지직 보관함')


def remember_library(root):
    if FROZEN:
        save_settings(library=root)


def diagnose():
    from . import compute
    import numpy, soundfile, sherpa_onnx
    from importlib.metadata import version
    tools = {}
    for name, flag in [('ffmpeg','-version'),('ffprobe','-version'),('whisper-cli','--version'),('llama-completion','--version'),('llama-tokenize','--version'),('llama-server','--version')]:
        file = shutil.which(name)
        if not file: raise RuntimeError(f'{name} 실행 파일이 없습니다')
        r = subprocess.run([file, flag],capture_output=True,text=True,timeout=15)
        if r.returncode: raise RuntimeError(f'{name} 실행 실패')
        tools[name] = {'path':file,'version':(r.stdout+r.stderr).splitlines()[0]}
    return {'frozen':FROZEN,'python':sys.version,'executable':sys.executable,'tools':tools,
            'engines':{name:version(name) for name in ['yt-dlp','sherpa-onnx','numpy','soundfile']},
            'certificate':os.environ.get('SSL_CERT_FILE'), 'compute':compute.status()}
