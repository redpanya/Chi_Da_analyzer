"""고정된 보컬용 BS-Roformer. 기존 SAM 모델과 저장 위치를 공유하지 않는다."""
from pathlib import Path
import shutil
import sys
from urllib.request import Request, urlopen

from . import model_paths
from .source import check_cancel
from .speech_model import digest
from .storage import ProjectLock, read_json, save_json

from .roformer_config import NAME, REVISION, FILENAME, FILES, PROFILES, profile

def home(): return model_paths.root()/'separation'/'bs-roformer-viperx-1297'/REVISION

def engine():
    if getattr(sys, 'frozen', False): return [str(Path(sys._MEIPASS).parent.parent/'roformer'/'roformer-worker')]
    root=Path(__file__).resolve().parents[1]
    return [str(root/'.roformer-venv/bin/python'), str(root/'workers/roformer.py')]

def paths():
    root=home()
    if any(p.is_symlink() for p in [root, *root.parents]): raise ValueError('모델 연결 경로는 지원하지 않습니다')
    if any((root/name).is_symlink() for name,*_ in FILES): raise ValueError('모델 연결 파일은 지원하지 않습니다')
    return [(root/name,size,sha,url) for name,size,sha,url in FILES]

def fingerprints(): return {p.name:[p.stat().st_size,p.stat().st_mtime_ns] for p,n,_,_ in paths() if p.is_file() and p.stat().st_size==n}

def status():
    try:
        values=fingerprints();ready=len(values)==len(FILES) and read_json(home()/'verified.json')==values
    except (OSError,ValueError): ready=False
    return {'name':NAME,'ready':ready,'engine':Path(engine()[0]).is_file(),'bytes':sum(f[1] for f in FILES),
            'path':str(home()),'profiles':PROFILES,'speed_note':'M1 Pro 16GB의 빠름 설정에서 약 5분 음원 분리에 6분 39초가 걸렸습니다(단일 측정·로딩/전사 제외). 방송자·게임 대사·노래를 구별하지 않으며 전사 정확도 향상은 보장하지 않습니다.'}

def verify():
    model_paths.available()
    for p,size,sha,_ in paths():
        if not p.is_file() or p.stat().st_size!=size or digest(p)!=sha: raise ValueError('BS-Roformer 모델 준비·검사를 실행하세요')

def prepare(stop, update):
    model_paths.available()
    with ProjectLock(home()):
        for target,size,sha,url in paths():
            check_cancel(stop)
            if target.exists():
                if digest(target)==sha: continue
                raise ValueError('같은 이름의 다른 모델이 있습니다. 파일을 보존하고 별도 모델 폴더를 선택하세요')
            part=target.with_name(target.name+'.part')
            if part.is_symlink(): raise ValueError('모델 임시 연결 파일은 지원하지 않습니다')
            offset=part.stat().st_size if part.exists() else 0
            if offset>size: raise ValueError('모델 임시 파일 크기가 잘못됐습니다')
            if shutil.disk_usage(home()).free<size-offset+256*1024**2: raise OSError('모델 저장 공간이 부족합니다')
            if offset<size:
                request=Request(url,headers={'Range':f'bytes={offset}-'} if offset else {})
                with urlopen(request,timeout=30) as response:
                    if response.status==200: offset=0
                    elif response.status!=206 or not response.headers.get('Content-Range','').startswith(f'bytes {offset}-'): raise ValueError('모델 이어받기 범위가 잘못됐습니다')
                    with part.open('ab' if offset else 'wb') as out:
                        while block:=response.read(1024*1024):
                            check_cancel(stop);out.write(block);offset+=len(block)
                            if offset>size: raise ValueError('모델 파일이 예상 크기를 넘었습니다')
                            update(message='BS-Roformer 준비: '+target.name,progress={'bytes':offset,'total_bytes':size})
            if part.stat().st_size!=size or digest(part)!=sha: raise ValueError('모델 SHA-256 검사 실패. 임시 파일은 보존했습니다')
            check_cancel(stop);part.replace(target)
        save_json(home()/'verified.json',fingerprints())
