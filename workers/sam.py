"""SAM 전용 프로세스. 로컬 고정 가중치만 읽고 조각별 결과를 보존한다."""
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from archive.sam_options import ode_options
from archive.audio_limits import wav_format

def save(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False));tmp.replace(path)

def load_model(folder):
    import mlx.core as mx
    from mlx_audio.sts.models.sam_audio.model import SAMAudio
    from mlx_audio.sts.models.sam_audio.config import SAMAudioConfig
    from mlx_audio.sts.models.sam_audio.text_encoder import T5Encoder,T5Config
    from transformers import AutoTokenizer
    from mlx.utils import tree_flatten
    # 라이브러리의 경고 후 임의 가중치 반환 경로를 피하고 누락을 오류로 처리한다.
    model=SAMAudio(SAMAudioConfig.from_dict(json.loads((folder/'sam/config.json').read_text(encoding='utf-8'))))
    weights={}
    for file in sorted((folder/'sam').glob('model-*.safetensors')):weights.update(mx.load(str(file)))
    model.load_weights(list(model.sanitize(weights).items()),strict=True)
    del weights
    model.eval();mx.eval(model.parameters());mx.clear_cache()
    c=json.loads((folder/'t5/config.json').read_text(encoding='utf-8'))
    # t5-base의 일반 ReLU FFN을 사용한다. MLX 기본값은 gated T5 1.1이다.
    c.update(is_gated_act=False,dense_act_fn='relu')
    config=T5Config(**{k:v for k,v in c.items() if k in T5Config.__dataclass_fields__})
    t5=T5Encoder(config)
    weights=T5Encoder.sanitize(mx.load(str(folder/'t5/model.safetensors')))
    keys=dict(tree_flatten(t5.parameters()))
    t5.load_weights([(k,v) for k,v in weights.items() if k in keys],strict=True)
    t5.eval();mx.eval(t5.parameters());del weights
    model.text_encoder.model=t5
    model.text_encoder.tokenizer=AutoTokenizer.from_pretrained(str(folder/'t5'),local_files_only=True)
    mx.clear_cache()
    return model

def main(file):
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1';os.environ['TOKENIZERS_PARALLELISM']='false'
    args=json.loads(Path(file).read_text(encoding='utf-8'));ode = ode_options(args['contract'])
    folder=Path(args['output']);folder.mkdir(parents=True,exist_ok=True)
    parent=os.getppid()
    def watch():
        while True:
            time.sleep(.5)
            if os.getppid()!=parent:os.kill(os.getpid(),signal.SIGTERM)
    threading.Thread(target=watch,daemon=True).start()
    import hashlib
    import numpy as np
    import soundfile as sf
    import mlx.core as mx
    started=time.monotonic();model=load_model(Path(args['models']))
    print(json.dumps({'stage':'loaded','seconds':time.monotonic()-started}),flush=True)
    text,mask=model.text_encoder(['speech']);mx.eval(text,mask)
    rate=48000;chunk=10*rate;overlap=3*rate;hop=chunk-overlap
    with sf.SoundFile(args['audio']) as source:
        if source.samplerate!=rate or source.channels!=1:raise ValueError('SAM 입력은 48kHz 모노여야 합니다')
        frames=len(source);wav_format(frames,rate,1);starts=list(range(0,max(1,frames-overlap),hop));entries=[]
        for index,start in enumerate(starts):
            size=min(chunk,frames-start);path=folder/f'{index:06}.npz';meta=path.with_suffix('.json')
            signature={'start':start,'frames':size,'seed':42+index,'contract':args['contract']}
            cached=False
            if path.exists() and meta.exists():
                saved=json.loads(meta.read_text(encoding='utf-8'))
                cached=saved.get('signature')==signature and hashlib.sha256(path.read_bytes()).hexdigest()==saved.get('sha256')
                if not cached:raise ValueError('분리 조각이 변경됐습니다. 새 분리 실행이 필요합니다')
            if not cached:
                source.seek(start);audio=source.read(size,dtype='float32');mx.random.seed(42+index)
                result=model.separate(mx.array(audio[None,None,:]),['speech'],ode_opt=ode,ode_decode_chunk_size=50,_text_features=text,_text_mask=mask)
                target=np.asarray(result.target[0]).reshape(-1)[:size];residual=np.asarray(result.residual[0]).reshape(-1)[:size]
                if len(target)!=size or len(residual)!=size or not np.isfinite(target).all() or not np.isfinite(residual).all():raise ValueError('SAM 출력 길이 또는 수치가 올바르지 않습니다')
                raw_rms=float(np.sqrt(np.mean(audio**2)));voice_rms=float(np.sqrt(np.mean(target**2)))
                review=raw_rms>.005 and voice_rms<raw_rms*.01
                with path.with_suffix('.part').open('wb') as out:np.savez(out,target=target,residual=residual)
                path.with_suffix('.part').replace(path)
                save(meta,{'signature':signature,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'raw_rms':raw_rms,'voice_rms':voice_rms,'review':review})
                del result,target,residual;mx.clear_cache()
            entries.append(str(path));save(folder/'progress.json',{'processed_ms':round((start+size)/rate*1000),'duration_ms':round(frames/rate*1000),'chunks':len(entries)})
            print(json.dumps({'chunk':index,'cached':cached,'seconds':time.monotonic()-started}),flush=True)
    reviews=[i for i,p in enumerate(entries) if json.loads(Path(p).with_suffix('.json').read_text(encoding='utf-8')).get('review')]
    for name in ('target','residual'):
        pending=folder/(name+'.part.wav');written=0;tail=None
        with sf.SoundFile(str(pending),'w',samplerate=rate,channels=1,subtype='FLOAT',format=wav_format(frames,rate,1)) as out:
            for i,p in enumerate(entries):
                with np.load(p) as data:current=data[name].copy()
                if tail is not None:
                    n=min(len(tail),len(current));ramp=np.linspace(0,1,n,dtype=np.float32)
                    current[:n]=tail[:n]*(1-ramp)+current[:n]*ramp
                keep=0 if i==len(entries)-1 else overlap
                ready=current if not keep else current[:-keep]
                out.write(ready);written+=len(ready);tail=current[-keep:].copy() if keep else None
        if written!=frames:raise ValueError('분리 조각 연결 길이가 일치하지 않습니다')
        pending.replace(folder/(name+'.wav'))
    save(folder/'result.json',{'frames':frames,'sample_rate':rate,'seconds':round(time.monotonic()-started,3),'peak_memory_bytes':mx.get_peak_memory(),'review_chunks':reviews,'contract':args['contract'],'hashes':{name:hashlib.file_digest((folder/(name+'.wav')).open('rb'),'sha256').hexdigest() for name in ('target','residual')}})

if __name__=='__main__':main(sys.argv[1])
