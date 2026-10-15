"""고정 GGUF의 해시 검증·이어받기. Qwen의 이전 캐시 경로도 유지한다."""
import shutil
from urllib.request import Request, urlopen
from .speech_model import digest
from . import model_paths
from .source import check_cancel
from .storage import ProjectLock, read_json, save_json

def home(): return model_paths.root()/'context'
NAME = 'Qwen3-8B-Q4_K_M'
DEFAULT_NAME = 'gemma-4-E4B-it-Q4_K_M'
SIZE = 5027783488
SHA256 = 'd98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785'
URL = 'https://huggingface.co/Qwen/Qwen3-8B-GGUF/resolve/7c41481f57cb95916b40956ab2f0b139b296d974/Qwen3-8B-Q4_K_M.gguf'

def spec(name=None):
    from .context_catalog import MODELS
    name = DEFAULT_NAME if name is None else name
    if name==NAME:return {'name':NAME,'size':SIZE,'sha256':SHA256,'url':URL}
    if not isinstance(name,str) or name not in MODELS:raise ValueError('지원하는 문맥 모델을 선택하세요')
    return dict(MODELS[name])

def model_path(name=None): return home()/(spec(name)['name']+'.gguf')

def verified_path(name=None):
    return home()/('verified.json' if spec(name)['name']==NAME else spec(name)['name']+'.verified.json')

def status(name=None):
    info=spec(name);folder=home();p=model_path(name);ready=False
    try: ready=not folder.is_symlink() and not p.is_symlink() and p.stat().st_size==info['size'] and read_json(verified_path(name))=={'sha256':info['sha256'],'mtime_ns':p.stat().st_mtime_ns}
    except (OSError,ValueError,TypeError): pass
    thinking=info['name']==DEFAULT_NAME
    return {'name':info['name'],'bytes':info['size'],'ready':ready,'thinking':thinking,
            'label':'Gemma 4 E4B · 사고 켜기' if thinking else info['name']+' · 사고 끄기',
            'engine':bool(shutil.which('llama-server' if thinking else 'llama-completion'))}

def prepare(stop, update, name=None):
    info=spec(name);size,sha,url=info['size'],info['sha256'],info['url']
    model_paths.available()
    folder=home()
    if folder.is_symlink(): raise ValueError('요약 모델 캐시의 연결 폴더는 지원하지 않습니다')
    with ProjectLock(folder):
        target=model_path(name);part=folder/(info['name']+'.part')
        if target.is_symlink() or part.is_symlink(): raise ValueError('모델 연결 파일은 지원하지 않습니다')
        if target.is_file() and target.stat().st_size==size and digest(target)==sha:
            save_json(verified_path(name),{'sha256':sha,'mtime_ns':target.stat().st_mtime_ns});return
        if target.exists():raise ValueError('동일 이름의 다른 모델 파일이 있습니다. 원본을 보존하고 별도 폴더를 선택하세요')
        offset=part.stat().st_size if part.exists() else 0
        if offset>size: raise ValueError('모델 임시 파일 크기가 잘못됐습니다. 해당 .part 파일을 다른 곳으로 옮기세요')
        if shutil.disk_usage(folder).free<size-offset+256*1024**2: raise OSError('요약 모델 저장 공간이 부족합니다')
        if offset<size:
            request=Request(url,headers={'Range':f'bytes={offset}-'} if offset else {})
            with urlopen(request,timeout=20) as response:
                if response.status==206:
                    if not response.headers.get('Content-Range','').startswith(f'bytes {offset}-'): raise ValueError('모델 이어받기 범위가 맞지 않습니다')
                elif response.status==200: offset=0
                else: raise ValueError('모델 다운로드 응답을 확인할 수 없습니다')
                with part.open('ab' if offset else 'wb') as file:
                    while True:
                        check_cancel(stop);block=response.read(1024*1024)
                        if not block:break
                        file.write(block);offset+=len(block)
                        if offset>size:raise ValueError('모델 파일 크기가 예상 범위를 넘었습니다')
                        update(message='요약 모델 다운로드 중',progress={'bytes':offset,'total_bytes':size})
        check_cancel(stop);update(message='요약 모델 SHA-256 검사 중')
        if part.stat().st_size!=size or digest(part)!=sha:
            part.rename(part.with_name(part.name+'.invalid-'+str(part.stat().st_mtime_ns)))
            raise ValueError('요약 모델 검사에 실패했습니다. 다시 준비하세요')
        check_cancel(stop);part.replace(target)
        save_json(verified_path(name),{'sha256':sha,'mtime_ns':target.stat().st_mtime_ns})
