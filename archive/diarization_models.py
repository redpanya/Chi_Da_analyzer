"""고정 리비전 파일별 검사. 다른 엔진/이전 모델은 이동·삭제하지 않는다."""
import hashlib
import shutil
import urllib.request

from . import diarization_backends as backends, model_paths, voice_models
from .source import check_cancel
from .storage import ProjectLock, save_json


def local(backend, name):
    root = backends.home(backend)
    target = root/name
    if not target.resolve().is_relative_to(root.resolve()): raise ValueError('모델 경로가 올바르지 않습니다')
    for p in (target,*target.parents):
        if p.is_symlink(): raise ValueError('모델의 연결 파일·폴더는 사용할 수 없습니다')
        if p == model_paths.root(): break
    return target


def fingerprints(backend):
    if backend=='fluid' and local(backend,'.fluidaudio-revision').read_text(encoding='utf-8').strip()!=backends.catalog(backend)['revision']:
        raise ValueError('FluidAudio 모델 리비전을 다시 검사하세요')
    return {f['name']:[p.stat().st_size,p.stat().st_mtime_ns] for f in backends.catalog(backend)['files'] for p in [local(backend,f['name'])]}


def matches(file, spec, stop=None):
    if not file.is_file() or file.stat().st_size != spec['size']: return False
    sha = hashlib.sha256() if spec['sha256'] else hashlib.sha1(f"blob {spec['size']}\0".encode())
    with file.open('rb') as source:
        while block := source.read(1024*1024):
            if stop is not None: check_cancel(stop)
            sha.update(block)
    return sha.hexdigest() == (spec['sha256'] or spec['git_sha1'])


def verify(backend, stop=None):
    if backend == 'sherpa': return voice_models.verify()
    model_paths.available()
    for spec in backends.catalog(backend)['files']:
        if not matches(local(backend,spec['name']),spec,stop):
            raise ValueError('화자 모델이 없거나 손상됐습니다. 선택 모델 준비·검사를 실행하세요')
    if backend=='fluid': fingerprints(backend)


def download(backend, stop, update):
    model_paths.available()
    folder = local(backend,''); folder.mkdir(parents=True,exist_ok=True)
    spec = backends.catalog(backend)
    with ProjectLock(folder):
        if shutil.disk_usage(folder).free < sum(f['size'] for f in spec['files'])+128*1024**2:
            raise ValueError('화자 모델 다운로드 여유 공간이 부족합니다')
        for entry in spec['files']:
            check_cancel(stop)
            target = local(backend,entry['name'])
            if matches(target,entry,stop): continue
            target.parent.mkdir(parents=True,exist_ok=True)
            update(message='화자 모델 준비: '+entry['name'],progress={})
            part = local(backend,entry['name']+'.part')
            url = f"https://huggingface.co/{spec['repo']}/resolve/{spec['revision']}/{entry['name']}"
            with urllib.request.urlopen(url,timeout=45) as source, part.open('wb') as output:
                count=0
                while block := source.read(1024*1024):
                    check_cancel(stop); output.write(block); count+=len(block)
                    if count>entry['size']: raise ValueError('공식 모델 파일 크기가 달라졌습니다')
                    update(message='화자 모델 준비: '+entry['name'],progress={'bytes':count,'total_bytes':entry['size']})
            if not matches(part,entry,stop): raise ValueError('다운로드한 화자 모델의 해시가 다릅니다')
            part.replace(target)
            if not matches(target,entry,stop): raise ValueError('다운로드한 화자 모델 검사 실패')
        if backend=='fluid':
            local(backend,'.fluidaudio-revision').write_text(spec['revision']+'\n')
        verify(backend,stop)
        save_json(local(backend,'verified.json'),{'signature':backends.signature(backend),'files':fingerprints(backend)})
