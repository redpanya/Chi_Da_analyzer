"""화자 엔진 선택과 실행 능력. 상태 조회는 다운로드나 모델 로드를 하지 않는다."""
from pathlib import Path
import platform
import sys

from . import voice_models, model_paths
from .storage import read_json

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / '.diarization-tools'
BACKENDS = {
    'sherpa': {'label':'sherpa-onnx · 기존', 'hint':'CPU · 30분 조각 이어받기 · 기존 결과 호환', 'manual_speakers':True, 'resume':True},
    'pyannote': {'label':'pyannote.audio + Community-1', 'hint':'PyTorch MPS · 중단하면 처음부터 재실행', 'manual_speakers':True, 'resume':False},
    'fluid': {'label':'FluidAudio 오프라인 · Community-1 계열', 'hint':'CoreML · Apple Silicon · VBx 화자 연결 · 중단하면 처음부터 재실행', 'manual_speakers':True, 'resume':False},
}


def checked(backend):
    if not isinstance(backend,str) or backend not in BACKENDS: raise ValueError('지원하는 화자 엔진을 선택하세요')
    return backend


def validate(backend, speakers=-1):
    checked(backend)
    if type(speakers) is not int or speakers not in [-1,*range(1,21)]:
        raise ValueError('화자 수는 자동 또는 1~20명을 선택하세요')


def executable(backend):
    checked(backend)
    from . import speaker_tools
    return speaker_tools.resolve(backend)[0]


def catalog(backend):
    return read_json(Path(__file__).with_name('diarization_catalog.json'))[checked(backend)]


def home(backend):
    checked(backend)
    if backend == 'sherpa': return voice_models.home()
    folder = model_paths.root()/'voices'/backend/catalog(backend)['revision']
    return folder/'speaker-diarization' if backend=='fluid' else folder


def signature(backend):
    if backend == 'sherpa':
        return {'models':{n:v[1] for n,v in voice_models.FILES.items()},'segmentation_sha256':voice_models.SEG_SHA,'version':1}
    return {'backend':backend,'revision':catalog(backend)['revision'],
            'engine_revision':{'pyannote':'4.0.7-torch2.8.0-mps','fluid':'224de0fb3c304b41bbae24e85e1801900865ff3e'}[backend], 'version':1}


def status(backend):
    from .diarization_models import fingerprints
    from . import speaker_tools
    checked(backend)
    if backend == 'sherpa': info = voice_models.status()
    else:
        try:
            saved = read_json(home(backend)/'verified.json')
            ready = saved['signature'] == signature(backend) and saved['files'] == fingerprints(backend)
        except (OSError, ValueError, KeyError, TypeError): ready = False
        info = {'ready':ready,'engine':executable(backend).is_file(),
                'bytes':sum(f['size'] for f in catalog(backend)['files']), 'free_bytes':model_paths.free_bytes()}
    tool = speaker_tools.status(backend)
    supported = tool['supported']
    hint = '‘실행 도구 다운로드·설치’ 후 ‘선택 모델 준비·검사’를 실행하세요.'
    details = dict(BACKENDS[backend])
    if backend == 'pyannote' and sys.platform == 'win32': details['hint'] = 'PyTorch CPU · 별도 엔진 설치 · 중단하면 처음부터 재실행'
    return info | details | {'id':backend,'supported':supported,'path':str(home(backend)),
        'engine':tool['ready'], 'tool':tool,
        'install_hint':hint if supported else '현재 장치에서 지원하지 않는 실행 도구입니다. FluidAudio는 Apple Silicon macOS 전용입니다.'}
