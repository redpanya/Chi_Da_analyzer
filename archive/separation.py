"""전사 전 전체 음성·선택 구간이 공유하는 SAM 실행과 보존 계약."""
import hashlib
import json
import shutil
import subprocess
from . import processes
import time
import uuid
import wave

from . import sam_models, sam_options, speech_media as media, speech_model, speech_store as store
from . import audio_limits
from .source import check_cancel, Cancelled
from .storage import read_json, save_json, stamp

def contract(profile="standard"):
    return {'model':sam_models.NAME,'revision':sam_models.REVISION,'runtime':'mlx-audio/0.5.9',
            'rate':48000,'chunk_seconds':10,'overlap_seconds':3,'seed':42,'description':'speech','ode':sam_options.profile(profile)['ode'],'version':1}

def validate(file,duration_ms,rate=48000):
    # ffprobe는 영상 전용 검사와 분리하여 오디오 형식·길이만 검사한다.
    result=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(file)],capture_output=True,timeout=30)
    if result.returncode:raise ValueError('음성 분리 파일을 읽을 수 없습니다')
    value=json.loads(result.stdout);stream=value['streams'][0]
    if int(stream.get('sample_rate',0))!=rate or stream.get('channels')!=1 or abs(float(value['format']['duration'])*1000-duration_ms)>1:
        raise ValueError('분리 전후 음성 형식·길이가 일치하지 않습니다')

def run_worker(folder,wav,stop,lock,update,profile="standard"):
    request=folder/'request.json';save_json(request,{'models':str(sam_models.home()),'audio':str(wav),'output':str(folder),'contract':contract(profile)})
    with (folder/f'engine-{uuid.uuid4().hex}.log').open('wb') as log:
        child=processes.popen([*sam_models.engine(),str(request)],stdout=log,stderr=subprocess.STDOUT,lock_fd=lock.fd)
        previous=None
        try:
            while child.poll() is None:
                if stop.wait(.25):raise Cancelled()
                progress=folder/'progress.json'
                if progress.exists():
                    value=read_json(progress)
                    if value!=previous:update(message='SAM 음성 분리 · 완료 조각 보존 중',progress=value);previous=value
            check_cancel(stop)
            if child.returncode:raise ValueError(f'SAM 음성 분리에 실패했습니다 ({child.returncode}). 분리 실행 폴더의 engine 로그를 확인하세요')
        finally:
            processes.stop(child, timeout=8)
    return read_json(folder/'result.json')

def extract48(path,data,track,folder,stop,lock,start_ms=0,end_ms=None):
    details=media.info(path,data);end_ms=end_ms or details['duration_ms']
    if track not in {t['index'] for t in details['tracks']}:raise ValueError('오디오 트랙을 선택하세요')
    duration=end_ms-start_ms
    if not 0<=start_ms<end_ms<=details['duration_ms']:raise ValueError('분리 범위가 잘못됐습니다')
    audio_limits.duration(duration)
    wav=folder/'source48.wav'
    if not wav.exists():
        part=folder/'source48.part.wav'
        filter=f"asetpts=PTS-({details['origin_seconds']})/TB,aresample=48000:async=1:first_pts=0,apad,atrim=start_sample={start_ms*48}:end_sample={end_ms*48},asetpts=PTS-STARTPTS"
        media.process(['ffmpeg','-nostdin','-v','error','-y','-copyts','-i',str(media.source(path,data)),'-map',f'0:{track}','-vn','-af',filter,'-ac','1','-ar','48000','-c:a','pcm_s16le','-rf64','auto',str(part)],folder/'extract48.log',stop,lock)
        validate(part,duration);check_cancel(stop);part.replace(wav)
    validate(wav,duration)
    return wav

def whole(path,data,stop,lock,update,profile="standard"):
    settings = contract(profile)
    state=store.state(path);raw=state.get('raw_audio') or state.get('audio')
    if not raw:raise ValueError('원음을 먼저 추출하세요')
    audio_limits.duration(raw['duration_ms'])
    if raw['source']!=media.identity(media.source(path,data),path) or speech_model.digest(media.local(path,raw['file']),stop)!=raw['sha256']:
        raise ValueError('원음이 변경됐습니다. 새로 추출하세요')
    sam_models.verify()
    signature={'source':raw['source'],'raw_sha256':raw['sha256'],'track':raw['track'],'contract':settings}
    key=hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest()
    folder=media.local(path,'separations/'+key);folder.mkdir(parents=True,exist_ok=True)
    if any(p.is_symlink() for p in folder.iterdir()):raise ValueError('분리 폴더의 연결 파일은 사용할 수 없습니다')
    cached = completed(folder, profile, stop)
    # 겹치는 float 조각과 두 출력, 48kHz 원음, 16kHz 전사용 사본을 함께 계산한다.
    if not cached and shutil.disk_usage(path).free<audio_limits.remaining_space(folder,raw['duration_ms'],1200,128*1024**2):
        raise OSError('원음·분리음·겹침 조각 저장 공간이 부족합니다 (영상 1시간당 약 4.3GB 여유 필요)')
    if not (folder/'manifest.json').exists():save_json(folder/'manifest.json',signature|{'created_at':stamp()})
    elif read_json(folder/'manifest.json')!=signature|{'created_at':read_json(folder/'manifest.json')['created_at']}:raise ValueError('분리 실행 조건이 달라졌습니다')
    update(message='SAM 완료 결과 확인 중' if cached else 'SAM 모델 로딩·음성 분리 중',progress={},separation_run=key)
    if cached: result=cached
    else:
        wav=extract48(path,data,raw['track'],folder,stop,lock)
        result=run_worker(folder,wav,stop,lock,update,profile)
    for name in ('target','residual'):validate(folder/(name+'.wav'),raw['duration_ms'])
    # 에너지 감소는 음악·무음일 수도 있어 품질 확인 표시만 남긴다.
    update(separation_review_chunks=result['review_chunks'])
    converted=folder/'speech16.wav'
    if not converted.exists():
        part=folder/'speech16.part.wav'
        media.process(['ffmpeg','-nostdin','-v','error','-y','-i',str(folder/'target.wav'),'-af',f"aresample=16000,apad,atrim=end_sample={raw['duration_ms']*16}",'-ac','1','-ar','16000','-c:a','pcm_s16le',str(part)],folder/'resample.log',stop,lock)
        media.validate_wav(part,raw['duration_ms'],stop);part.replace(converted)
    media.validate_wav(converted,raw['duration_ms'],stop)
    if raw['source']!=media.identity(media.source(path,data),path):raise ValueError('분리 중 영상이 변경됐습니다')
    audio=raw|{'file':str(converted.relative_to(path/'speech')),'sha256':speech_model.digest(converted,stop),'input_kind':'sam','sam_profile':profile,'separation_run':key,
               'target':str((folder/'target.wav').relative_to(path/'speech')),'residual':str((folder/'residual.wav').relative_to(path/'speech'))}
    update(separated_audio=audio)
    return raw,audio


def completed(folder, profile="standard", stop=None):
    file = folder/'result.json'
    if not file.exists(): return None
    result = read_json(file)
    if result.get('contract') != contract(profile): return None
    for name in ('target','residual'):
        output = folder/(name+'.wav')
        if not output.is_file() or output.is_symlink() or speech_model.digest(output,stop) != result.get('hashes', {}).get(name):
            raise ValueError('기존 분리 결과가 변경됐습니다. 해당 파일을 보존하고 새 보관함에서 다시 처리하세요')
    return result
