"""추가 엔진 실행과 공통 결과 변환. 자동으로 다른 엔진에 대체하지 않는다."""
import sys

from . import diarization_backends as backends, diarization_models as models, speech_media as media, voice_models, speaker_tools
from .storage import read_json, save_json


def process(backend,folder,request,stop,lock,update):
    engine=backends.executable(backend)
    if not engine.is_file(): raise ValueError(backends.status(backend)['install_hint'])
    for name in ('error.json','progress.json','engine.json'):
        (folder/name).unlink(missing_ok=True)
    save_json(folder/'request.json',request)
    previous=None
    def progress():
        nonlocal previous
        file=folder/'progress.json'
        if file.exists():
            value=read_json(file)
            if value!=previous:
                previous=value
                count=f" {value.get('completed',0)}/{value['total']}" if value.get('total') else ''
                update(message=value.get('message') or ('화자 구분 · '+value.get('phase','처리 중')+count),progress=value.get('progress',{}))
    if backend=='pyannote':
        args=speaker_tools.command(backend,folder/'request.json')
    elif backend=='fluid': args=[str(engine),str(folder/'request.json')]
    else: raise ValueError('지원하지 않는 추가 화자 엔진입니다')
    try: media.process(args,folder/'engine.log',stop,lock,on_poll=progress)
    except ValueError:
        if (folder/'error.json').exists(): raise ValueError(read_json(folder/'error.json')['message']) from None
        raise
    return read_json(folder/'engine.json')


def prepare(backend,folder,stop,lock,update):
    if backend=='sherpa': return voice_models.prepare(stop,update)
    status=backends.status(backend)
    if not status['supported'] or not status['engine']: raise ValueError(status['install_hint'])
    if backend=='pyannote':
        from . import model_paths
        folder.mkdir(parents=True,exist_ok=True)
        target=models.local(backend,''); target.mkdir(parents=True,exist_ok=True)
        from .storage import ProjectLock
        with ProjectLock(target):
            for entry in backends.catalog(backend)['files']: models.local(backend,entry['name'])
            # 이미 검증 가능한 모델에는 재로그인·재다운로드를 요구하지 않는다.
            try: models.verify(backend,stop)
            except (OSError, ValueError):
                process(backend,folder,{'action':'prepare','model_root':str(model_paths.root()),'output':str(folder/'engine.json')},stop,lock,update)
            models.verify(backend,stop)
            save_json(target/'verified.json',{'signature':backends.signature(backend),'files':models.fingerprints(backend)})
    else: models.download(backend,stop,update)


def run(backend,folder,audio,speakers,stop,lock,update):
    backends.validate(backend,speakers)
    models.verify(backend,stop)
    folder.mkdir(parents=True,exist_ok=True)
    cache=backends.home(backend)
    # FluidAudio는 부모 캐시 아래에 공식 저장소명 폴더를 찾는다.
    if backend=='fluid': cache=cache.parent
    return process(backend,folder,{'action':'diarize','audio':str(audio),'cache':str(cache),'speakers':speakers,
                                  'output':str(folder/'engine.json')},stop,lock,update)
