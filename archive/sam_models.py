"""SAM·T5 고정 파일 준비. 기존 음성 모델과 저장 상태를 분리한다."""
import json
from pathlib import Path
import shutil
import sys
from urllib.request import Request, urlopen

from . import model_paths, sam_options
from .speech_model import digest
from .storage import ProjectLock, read_json, save_json
from .source import check_cancel

CATALOG = json.loads(Path(__file__).with_name('sam_catalog.json').read_text(encoding='utf-8'))
NAME = 'sam-audio-large-fp16'
REVISION = CATALOG[0]['revision']

def home(): return model_paths.root()/'separation'/NAME/REVISION

def engine():
    if getattr(sys, 'frozen', False):
        return [str(Path(sys._MEIPASS).parent.parent/'sam'/'sam-worker')]
    return [str(Path(__file__).resolve().parents[1]/'.sam-venv/bin/python'),
            str(Path(__file__).resolve().parents[1]/'workers/sam.py')]

def paths():
    folder = home()
    for part in [folder, *folder.parents]:
        if part.is_symlink(): raise ValueError('SAM 모델의 연결 경로는 지원하지 않습니다')
    result = [(folder/item['group']/item['name'], item) for item in CATALOG]
    if any(p.is_symlink() or p.parent.is_symlink() for p,_ in result):
        raise ValueError('SAM 모델 연결 파일은 지원하지 않습니다')
    return result

def fingerprints():
    return {str(p.relative_to(home())):[p.stat().st_size,p.stat().st_mtime_ns]
            for p,item in paths() if p.is_file() and p.stat().st_size==item['size']}

def status():
    try:
        values=fingerprints()
        ready=len(values)==len(CATALOG) and read_json(home()/'verified.json')==values
    except (OSError,ValueError): ready=False
    return {'name':NAME,'ready':ready,'engine':Path(engine()[0]).is_file(),
            'bytes':sum(item['size'] for item in CATALOG),'path':str(home()),
            'profiles':sam_options.PROFILES, 'speed_note':sam_options.SPEED_NOTE}

def verify():
    model_paths.available()
    for p,item in paths():
        if not p.is_file() or p.stat().st_size!=item['size'] or digest(p)!=item['sha256']:
            raise ValueError('SAM 모델이 없거나 손상됐습니다. 모델 준비·검사를 실행하세요')

def prepare(stop, update):
    model_paths.available()
    with ProjectLock(home()):
        for target,item in paths():
            check_cancel(stop)
            if target.is_file():
                if digest(target)==item['sha256']: continue
                raise ValueError('동일 이름의 다른 SAM 파일이 있습니다. 기존 파일을 보존하고 별도 모델 폴더를 선택하세요')
            target.parent.mkdir(exist_ok=True)
            part=target.with_name(target.name+'.part')
            if part.is_symlink(): raise ValueError('모델 임시 연결 파일은 지원하지 않습니다')
            offset=part.stat().st_size if part.exists() else 0
            if offset>item['size']: raise ValueError('SAM 임시 파일 크기가 예상 범위를 넘습니다')
            if shutil.disk_usage(home()).free < item['size']-offset+256*1024**2:
                raise OSError('SAM 모델 저장 공간이 부족합니다')
            if offset<item['size']:
                request=Request(item['url'], headers={'Range':f'bytes={offset}-'} if offset else {})
                with urlopen(request, timeout=30) as response:
                    if response.status==200: offset=0
                    elif response.status!=206 or not response.headers.get('Content-Range','').startswith(f'bytes {offset}-'):
                        raise ValueError('SAM 다운로드 이어받기 범위가 맞지 않습니다')
                    with part.open('ab' if offset else 'wb') as out:
                        while block:=response.read(1024*1024):
                            check_cancel(stop);out.write(block);offset+=len(block)
                            if offset>item['size']: raise ValueError('SAM 모델 파일이 예상 크기를 넘었습니다')
                            update(message='SAM 준비: '+item['name'],progress={'bytes':offset,'total_bytes':item['size']})
            update(message='SAM 파일 검사: '+item['name'])
            if part.stat().st_size!=item['size'] or digest(part)!=item['sha256']:
                raise ValueError('SAM 모델 SHA-256 검사가 실패했습니다. 임시 파일을 보존했습니다')
            check_cancel(stop);part.replace(target)
        save_json(home()/'verified.json',fingerprints())
