"""BS-Roformer 전사 전처리. 이전 SAM 실행 계약과 결과는 변경하지 않는다."""
import hashlib
import json
import shutil
import subprocess
from . import processes
import uuid

from . import roformer_models as models, speech_media as media, speech_model, speech_store as store
from . import audio_limits
from .source import Cancelled, check_cancel
from .storage import read_json, save_json, stamp

def contract(profile='fast'):
    p=models.profile(profile)
    return {'model':models.NAME,'revision':models.REVISION,'hashes':{f[0]:f[2] for f in models.FILES},
            'runtime':'audio-separator/0.47.0/torch-2.14.1','rate':44100,'channels':2,'chunk_seconds':60,
            'context_seconds':8,'overlap':p['overlap'],'fp16':p['fp16'],'gain':1,'version':1}

def validate(file,duration):
    result=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(file)],capture_output=True,timeout=30)
    if result.returncode:raise ValueError('분리 파일을 읽을 수 없습니다')
    value=json.loads(result.stdout);stream=value['streams'][0]
    if int(stream.get('sample_rate',0))!=44100 or stream.get('channels')!=2 or abs(float(value['format']['duration'])*1000-duration)>1:raise ValueError('분리 파일 형식·길이가 일치하지 않습니다')

def extract(path,data,track,folder,stop,lock,start_ms=0,end_ms=None):
    details=media.info(path,data);end_ms=details['duration_ms'] if end_ms is None else end_ms
    if track not in {t['index'] for t in details['tracks']} or not 0<=start_ms<end_ms<=details['duration_ms']:raise ValueError('음성 트랙 또는 범위가 잘못됐습니다')
    duration=end_ms-start_ms
    audio_limits.duration(duration)
    wav=folder/'source44.wav'
    if not wav.exists():
        part=folder/'source44.part.wav'
        a,b=round(start_ms*44.1),round(end_ms*44.1)
        filters=f"asetpts=PTS-({details['origin_seconds']})/TB,aresample=44100:async=1:first_pts=0,apad,atrim=start_sample={a}:end_sample={b},asetpts=PTS-STARTPTS"
        media.process(['ffmpeg','-nostdin','-v','error','-y','-copyts','-i',str(media.source(path,data)),'-map',f'0:{track}','-vn','-af',filters,'-ac','2','-ar','44100','-c:a','pcm_s16le','-rf64','auto',str(part)],folder/'extract44.log',stop,lock)
        validate(part,duration);check_cancel(stop);part.replace(wav)
    validate(wav,duration);return wav

def run_worker(folder,wav,stop,lock,update,profile='fast'):
    input_signature={'sha256':speech_model.digest(wav,stop),'bytes':wav.stat().st_size}
    if (folder/'input.json').exists():
        if read_json(folder/'input.json')!=input_signature:raise ValueError('분리 입력 사본이 변경됐습니다. 기존 조각과 섞지 않습니다')
    else:save_json(folder/'input.json',input_signature)
    request=folder/'request.json';save_json(request,{'models':str(models.home()),'audio':str(wav),'input_sha256':input_signature['sha256'],'output':str(folder),'contract':contract(profile)})
    with (folder/f'engine-{uuid.uuid4().hex}.log').open('wb') as log:
        child=processes.popen([*models.engine(),str(request)],stdout=log,stderr=subprocess.STDOUT,lock_fd=lock.fd)
        previous=None
        try:
            while child.poll() is None:
                if stop.wait(.25):raise Cancelled()
                if (folder/'progress.json').exists():
                    value=read_json(folder/'progress.json')
                    if value!=previous:update(message='BS-Roformer 음성 분리 · 완료 조각 보존 중',progress=value);previous=value
            check_cancel(stop)
            if child.returncode:raise ValueError(f'BS-Roformer 분리 실패 ({child.returncode}). 분리 폴더의 engine 로그를 확인하세요')
        finally:
            processes.stop(child, timeout=8)
    return read_json(folder/'result.json')

def completed(folder,profile='fast',stop=None):
    if not (folder/'result.json').exists():return None
    result=read_json(folder/'result.json')
    if result.get('contract')!=contract(profile):return None
    for name in ('target','residual'):
        file=folder/(name+'.wav')
        if not file.is_file() or file.is_symlink() or speech_model.digest(file,stop)!=result.get('hashes',{}).get(name):raise ValueError('기존 분리 파일이 변경됐습니다. 파일을 보존하고 새 보관함에서 처리하세요')
    return result

def whole(path,data,stop,lock,update,profile='fast'):
    settings=contract(profile);state=store.state(path);raw=state.get('raw_audio') or state.get('audio')
    if not raw:raise ValueError('원음을 먼저 추출하세요')
    audio_limits.duration(raw['duration_ms'])
    if raw['source']!=media.identity(media.source(path,data),path) or speech_model.digest(media.local(path,raw['file']),stop)!=raw['sha256']:raise ValueError('원음이 변경됐습니다. 새로 추출하세요')
    models.verify()
    signature={'source':raw['source'],'raw_sha256':raw['sha256'],'track':raw['track'],'contract':settings}
    key=hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest()
    folder=media.local(path,'separations/'+key);folder.mkdir(parents=True,exist_ok=True)
    if any(p.is_symlink() for p in folder.iterdir()):raise ValueError('분리 폴더의 연결 파일은 사용할 수 없습니다')
    cached=completed(folder,profile,stop)
    if not cached and shutil.disk_usage(path).free<audio_limits.remaining_space(folder,raw['duration_ms'],1800,256*1024**2):raise OSError('분리 저장 공간이 부족합니다 (1시간당 약 6.5GB 필요)')
    if not (folder/'manifest.json').exists():save_json(folder/'manifest.json',signature|{'created_at':stamp()})
    elif {k:v for k,v in read_json(folder/'manifest.json').items() if k!='created_at'}!=signature:raise ValueError('분리 실행 조건이 달라졌습니다')
    update(message='BS-Roformer 완료 결과 확인 중' if cached else 'BS-Roformer 모델 로딩·분리 중',progress={},separation_run=key)
    result=cached or run_worker(folder,extract(path,data,raw['track'],folder,stop,lock),stop,lock,update,profile)
    for name in ('target','residual'):validate(folder/(name+'.wav'),raw['duration_ms'])
    converted=folder/'speech16.wav'
    if not converted.exists():
        part=folder/'speech16.part.wav'
        media.process(['ffmpeg','-nostdin','-v','error','-y','-i',str(folder/'target.wav'),'-af',f"aresample=16000,apad,atrim=end_sample={raw['duration_ms']*16}",'-ac','1','-ar','16000','-c:a','pcm_s16le',str(part)],folder/'resample.log',stop,lock)
        media.validate_wav(part,raw['duration_ms'],stop);check_cancel(stop);part.replace(converted)
    media.validate_wav(converted,raw['duration_ms'],stop)
    converted_hash=speech_model.digest(converted,stop)
    receipt=folder/'speech16.json'
    converted_signature={'target_sha256':result['hashes']['target'],'sha256':converted_hash}
    if receipt.exists() and read_json(receipt)!=converted_signature:raise ValueError('전사용 분리음이 변경됐습니다. 기존 결과는 보존했습니다')
    if not receipt.exists():save_json(receipt,converted_signature)
    if raw['source']!=media.identity(media.source(path,data),path):raise ValueError('분리 중 영상이 변경됐습니다')
    audio=raw|{'file':str(converted.relative_to(path/'speech')),'sha256':converted_hash,'input_kind':'roformer','separation_profile':profile,
        'separation_run':key,'target':str((folder/'target.wav').relative_to(path/'speech')),'residual':str((folder/'residual.wav').relative_to(path/'speech'))}
    update(separated_audio=audio,separation_review_chunks=result['review_chunks']);return raw,audio
