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
    if backend != 'sherpa' and getattr(sys,'frozen',False):
        bundle = (Path(sys.executable).parent if sys.platform == 'win32' else Path(sys._MEIPASS).parent.parent) / 'diarization'
        return bundle / {'pyannote':'pyannote/pyannote-worker.exe' if sys.platform == 'win32' else 'pyannote/pyannote-worker',
                         'fluid':'fluid/archive-fluid-diarizer'}[backend]
    return {'sherpa':voice_models.PYTHON,
            'pyannote':TOOLS/('pyannote/venv/Scripts/python.exe' if sys.platform == 'win32' else 'pyannote/venv/bin/python'),
            'fluid':TOOLS/'fluid/Runner/.build/release/archive-fluid-diarizer'}[backend]


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
    checked(backend)
    if backend == 'sherpa': info = voice_models.status()
    else:
        try:
            saved = read_json(home(backend)/'verified.json')
            ready = saved['signature'] == signature(backend) and saved['files'] == fingerprints(backend)
        except (OSError, ValueError, KeyError, TypeError): ready = False
        info = {'ready':ready,'engine':executable(backend).is_file(),
                'bytes':sum(f['size'] for f in catalog(backend)['files']), 'free_bytes':model_paths.free_bytes()}
    supported = backend == 'sherpa' or (platform.system() == 'Darwin' and platform.machine() == 'arm64')
    if backend == 'pyannote' and sys.platform == 'win32': supported = True
    hint = ('앱에 포함된 실행기가 없으면 앱 패키지를 다시 복사하세요.' if getattr(sys,'frozen',False)
            else '소스 폴더의 ‘화자 엔진 도구 설치.command’에서 선택해 설치하세요.')
    if getattr(sys,'frozen',False) and (Path(sys._MEIPASS)/'basic-release.json').exists():
        hint = '기본 배포본에는 sherpa 실행기가 포함됩니다. 다른 엔진은 개발용 별도 설치가 필요합니다.'
    if sys.platform == 'win32':
        hint = '기본 포터블에는 sherpa 실행기가 포함됩니다. pyannote는 별도 엔진 설치가 필요합니다.'
    details = dict(BACKENDS[backend])
    if backend == 'pyannote' and sys.platform == 'win32': details['hint'] = 'PyTorch CPU · 별도 엔진 설치 · 중단하면 처음부터 재실행'
    return info | details | {'id':backend,'supported':supported,'path':str(home(backend)),
        'install_hint':hint if supported else 'FluidAudio는 Apple Silicon macOS에서 지원합니다.'}
