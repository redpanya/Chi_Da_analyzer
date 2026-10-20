"""M4 전용 실행 환경과 출처·해시가 고정된 로컬 모델."""
from pathlib import Path
import shutil
import tarfile
import urllib.request
import sys

from .speech_model import digest
from . import model_paths
from .storage import ProjectLock, read_json, save_json
from .source import check_cancel

def home(): return model_paths.root() / 'voices'
PYTHON = Path(sys.executable) if getattr(sys,'frozen',False) else Path(__file__).resolve().parent.parent / ('.voice-venv/Scripts/python.exe' if sys.platform == 'win32' else '.voice-venv/bin/python')
BASE = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/'
FILES = {
    'segmentation.tar.bz2': (BASE+'speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2', '24615ee884c897d9d2ba09bb4d30da6bb1b15e685065962db5b02e76e4996488', 6958444),
    'embedding.onnx': (BASE+'speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx', '1a331345f04805badbb495c775a6ddffcdd1a732567d5ec8b3d5749e3c7a5e4b', 39593761),
}
SEG_SHA = '220ad67ca923bef2fa91f2390c786097bf305bceb5e261d4af67b38e938e1079'


def fingerprints():
    folder = home()
    return {name: [p.stat().st_size, p.stat().st_mtime_ns] for name in [*FILES, 'segmentation.onnx'] if (p := folder/name).is_file() and not p.is_symlink()}


def status():
    from . import speaker_tools
    folder = home()
    try:
        current = fingerprints()
        saved = read_json(folder/('diarization-verified.json' if (folder/'diarization-verified.json').exists() else 'verified.json'))
        ready = len(current) == 3 and {k:saved.get(k) for k in current} == current
    except (OSError, ValueError):
        ready = False
    return {'ready': ready, 'engine': speaker_tools.resolve('sherpa')[0].is_file(), 'bytes': sum(v[2] for v in FILES.values()),
            'free_bytes': model_paths.free_bytes()}


def verify():
    model_paths.available()
    folder = home()
    if folder.is_symlink():
        raise ValueError('모델 캐시의 연결 폴더는 지원하지 않습니다')
    for name, (_, sha, _) in FILES.items():
        if (folder/name).is_symlink() or not (folder/name).is_file() or digest(folder/name) != sha:
            raise ValueError('M4 모델이 없거나 손상됐습니다. 모델 준비·검사를 실행하세요')
    if (folder/'segmentation.onnx').is_symlink() or digest(folder/'segmentation.onnx') != SEG_SHA:
        raise ValueError('화자 분할 모델을 다시 준비하세요')


def prepare(stop, update):
    model_paths.available()
    folder = home()
    if folder.is_symlink():
        raise ValueError('모델 캐시의 연결 폴더는 지원하지 않습니다')
    folder.mkdir(parents=True, exist_ok=True)
    with ProjectLock(folder):
        if shutil.disk_usage(folder).free < 256 * 1024**2:
            raise ValueError('M4 모델 준비에 필요한 저장 공간이 부족합니다')
        for name, (url, sha, size) in FILES.items():
            check_cancel(stop); target = folder/name; part = folder/(name+'.part')
            if target.is_symlink() or part.is_symlink():
                raise ValueError('모델 연결 파일은 지원하지 않습니다')
            if target.is_file() and digest(target) == sha:
                continue
            # 작은 모델 묶음은 파일 단위로 재시도한다. 검증 완료 모델은 다시 받지 않는다.
            with urllib.request.urlopen(url, timeout=30) as response, part.open('wb') as output:
                count = 0
                while block := response.read(1024*1024):
                    check_cancel(stop); output.write(block); count += len(block)
                    if count > size:
                        raise ValueError('공식 모델의 크기가 달라졌습니다')
                    update(message='M4 모델 준비: '+name, progress={'bytes': count, 'total_bytes': size})
            if count != size or digest(part) != sha:
                raise ValueError('모델 다운로드 검사 실패. 다시 준비하세요')
            part.replace(target)
        with tarfile.open(folder/'segmentation.tar.bz2') as archive:
            for name in ('model.onnx', 'LICENSE', 'README.md'):
                member = archive.getmember('sherpa-onnx-pyannote-segmentation-3-0/'+name)
                target = folder/('segmentation.onnx' if name == 'model.onnx' else 'segmentation-'+name)
                if target.is_symlink():
                    raise ValueError('모델 연결 파일은 지원하지 않습니다')
                with archive.extractfile(member) as source:
                    target.write_bytes(source.read())
        verify(); save_json(folder/'diarization-verified.json', fingerprints())
