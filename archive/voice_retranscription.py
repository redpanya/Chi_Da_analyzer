"""음원 분리 없이 선택 구간의 원음을 재전사해 별도 비교본으로 저장한다."""
import shutil
import uuid
from . import voice_store as store, speech_store, speech_media as media, speech_model
from .storage import read_json, save_json, stamp
from .source import check_cancel


def run(job):
    from .voices import validate_range
    state=speech_store.state(job.path);audio=state.get('raw_audio') or state.get('audio')
    transcript=speech_store.manifest(job.path)
    if not audio or not transcript:raise ValueError('원음과 기존 전사를 먼저 준비하세요')
    start,end=job.options.get('start_ms'),job.options.get('end_ms')
    validate_range(start,end,audio['duration_ms'])
    if audio['source']!=media.identity(media.source(job.path,job.data),job.path):raise ValueError('원음의 영상 입력이 바뀌었습니다')
    original=media.local(job.path,audio['file']);identity=media.identity(original,job.path)
    engine=shutil.which('whisper-cli');speech_model.verify()
    if not engine:raise ValueError('whisper-cli를 찾지 못했습니다')
    id=uuid.uuid4().hex;folder=store.local(job.path,f'retranscriptions/{id}');folder.mkdir(parents=True)
    job.update(message='분리 없이 선택 구간의 원음을 다시 전사합니다',progress={})
    media.process(['ffmpeg','-nostdin','-v','error','-y','-i',str(original),
                   '-ss',str(start/1000),'-t',str((end-start)/1000),'-ac','1','-ar','16000','-c:a','pcm_s16le',str(folder/'source.wav')],
                  folder/'extract.log',job.stop,job.lock)
    media.validate_wav(folder/'source.wav',end-start,job.stop)
    media.process([engine,'-m',str(speech_model.model_path()),'-f',str(folder/'source.wav'),'-l',transcript['language'],
                   '-oj','-of',str(folder/'transcript'),'-t','4','-np'],folder/'transcribe.log',job.stop,job.lock)
    result={'id':id,'created_at':stamp(),'start_ms':start,'end_ms':end,'transcript_run':transcript['id'],
            'audio_sha256':audio['sha256'],'language':transcript['language'],'input':'original',
            'segments':speech_store.normalize(speech_store.read_engine_output(folder/'transcript.json'),start,end,0)}
    check_cancel(job.stop)
    if (state!=speech_store.state(job.path) or identity!=media.identity(original,job.path)
            or audio['source']!=media.identity(media.source(job.path,job.data),job.path)):
        raise ValueError('재전사 중 입력이 변경됐습니다. 기존 결과는 보존됩니다')
    save_json(folder/'result.json',result)
    job.update(retranscription=id,retranscriptions=store.state(job.path).get('retranscriptions',[])+[{'id':id,'start_ms':start,'end_ms':end}])


def latest(path):
    state=store.state(path);id=state.get('retranscription')
    if not id:return None
    if id not in [r['id'] for r in state.get('retranscriptions',[])]:raise ValueError('저장된 재전사 비교본이 아닙니다')
    result=read_json(store.local(path,f'retranscriptions/{id}/result.json'))
    current=speech_store.state(path)
    return result|{'stale':current.get('run')!=result['transcript_run'] or result['audio_sha256'] not in
                  [current.get(key,{}).get('sha256') for key in ('audio','raw_audio') if current.get(key)]}
