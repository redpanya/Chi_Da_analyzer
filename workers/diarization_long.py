"""긴 원음을 제한된 창으로 처리한 뒤 대표 음성으로 전체 화자 ID를 연결한다."""
import hashlib
import json
from pathlib import Path

import numpy as np
import soundfile as sf

CHUNK_SECONDS = 1800
CONTEXT_SECONDS = 5
VERSION = 1


def windows(frames, rate, seconds=CHUNK_SECONDS):
    for start in range(0, frames, seconds * rate):
        end = min(frames, start + seconds * rate)
        yield start, end, max(0, start-CONTEXT_SECONDS*rate), min(frames, end+CONTEXT_SECONDS*rate)


def save(path, value):
    pending=path.with_suffix('.tmp')
    pending.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8');pending.replace(path)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def representative(audio, turns, speaker, rate):
    # 다른 화자와 겹치는 구간은 대표 음성에서 제외한다.
    candidates=[t for t in turns if t['speaker']==speaker and t['end_ms']-t['start_ms']>=1500
                and not any(u['speaker']!=speaker and u['start_ms']<t['end_ms'] and u['end_ms']>t['start_ms'] for u in turns)]
    pieces=[];left=30*rate
    for t in sorted(candidates,key=lambda t:t['end_ms']-t['start_ms'],reverse=True):
        a=t['start_ms']*rate//1000;b=min(t['end_ms']*rate//1000,a+min(left,10*rate))
        if b>a:pieces.append(audio[a:b]);left-=b-a
        if not left:break
    return np.concatenate(pieces) if pieces else np.empty(0,dtype='float32')


def run(request, engine, extractor, cluster, seconds=CHUNK_SECONDS):
    folder=Path(request['output']).parent/'chunks';folder.mkdir(exist_ok=True)
    config=request['signature']|{'chunk_seconds':seconds,'context_seconds':CONTEXT_SECONDS,'version':VERSION}
    all_turns=[];features=[];keys=[]
    with sf.SoundFile(request['audio']) as source:
        if source.samplerate!=16000 or source.channels!=1:raise ValueError('화자 입력은 16kHz 모노여야 합니다')
        rate=source.samplerate;frames=len(source)
        for index,(start,end,left,right) in enumerate(windows(frames,rate,seconds)):
            path=folder/f'{index:05}.json';signature=config|{'start':start,'end':end}
            if path.exists():
                envelope=json.loads(path.read_text(encoding='utf-8'));value=envelope['value']
                if envelope['sha256']!=digest(value) or value['signature']!=signature:raise ValueError('화자 복구 조각이 변경됐습니다')
            else:
                source.seek(left);audio=source.read(right-left,dtype='float32')
                local=[{'start_ms':round(t.start*1000),'end_ms':round(t.end*1000),'speaker':int(t.speaker)}
                       for t in engine.process(audio).sort_by_start_time()]
                lengths={t['speaker']:0 for t in local}
                for t in local:lengths[t['speaker']]+=t['end_ms']-t['start_ms']
                embeddings={}
                # 비정상적인 과분할에서도 군집화 행렬을 제한한다. 제외한 발언은 실패 표시한다.
                for speaker in sorted(lengths,key=lengths.get,reverse=True)[:64]:
                    sample=representative(audio,local,speaker,rate)
                    if len(sample)<2*rate:continue
                    stream=extractor.create_stream();stream.accept_waveform(rate,sample);stream.input_finished()
                    if not extractor.is_ready(stream):continue
                    vector=np.asarray(extractor.compute(stream),dtype='float32');norm=float(np.linalg.norm(vector))
                    if not np.isfinite(vector).all() or norm<1e-8:continue
                    embeddings[str(speaker)]=(vector/norm).tolist()
                turns=[]
                for t in local:
                    a=max(start*1000//rate,t['start_ms']+left*1000//rate)
                    b=min(end*1000//rate,t['end_ms']+left*1000//rate)
                    if a<b:turns.append(t|{'start_ms':a,'end_ms':b})
                value={'signature':signature,'turns':turns,'embeddings':embeddings}
                save(path,{'value':value,'sha256':digest(value)})
            for label,vector in value['embeddings'].items():keys.append((index,int(label)));features.append(vector)
            all_turns.extend(t|{'chunk':index} for t in value['turns'])
            progress={'processed_ms':end*1000//rate,'duration_ms':frames*1000//rate,'chunks':index+1}
            save(folder.parent/'progress.json',progress);print(json.dumps(progress),flush=True)
    labels=cluster(np.asarray(features,dtype='float32'),request['speakers']) if features else []
    if len(labels)!=len(keys) or any(not isinstance(v,(int,np.integer)) or v<0 for v in labels):raise ValueError('전체 화자 연결 결과가 잘못됐습니다')
    mapping=dict(zip(keys,map(int,labels)))
    turns=[{'start_ms':t['start_ms'],'end_ms':t['end_ms'],'speaker':mapping.get((t['chunk'],t['speaker']))} for t in all_turns]
    return {'turns':turns,'mode':'chunked-global-v1','chunk_seconds':seconds,'representatives':len(keys),
            'unmatched_turns':sum(t['speaker'] is None for t in turns),'requested_speakers':request['speakers'],'threshold':.9}
