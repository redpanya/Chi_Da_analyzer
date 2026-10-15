"""오프라인 MPS 분리. 60초 단위 체크포인트와 원본 샘플 수를 유지한다."""
import hashlib
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import resource
import signal
import sys
import threading
import time
import uuid

if not getattr(sys,'frozen',False): sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from archive.roformer_config import FILENAME
from archive.audio_limits import wav_format

def save(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False));temp.replace(path)

def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def load_model(models,folder,contract):
    import torch
    from audio_separator.separator import Separator
    class LocalSeparator(Separator):
        # 네트워크 목록의 변경으로 다른 가중치/설정이 로딩되는 것을 막는다.
        def download_model_files(self,name):
            return name,'MDXC','BS-Roformer-Viperx-1297',str(models/(FILENAME+'.ckpt')),str(models/(FILENAME+'.yaml'))
        def download_file_if_not_exists(self,*args): raise RuntimeError('고정된 로컬 모델만 사용할 수 있습니다')
    if not torch.backends.mps.is_available(): raise RuntimeError('BS-Roformer의 Mac GPU(MPS)를 사용할 수 없습니다')
    torch.set_num_threads(4)
    engine=LocalSeparator(log_level=logging.WARNING,model_file_dir=str(models),output_dir=str(folder),
        use_native_fp16=contract['fp16'],normalization_threshold=1,amplification_threshold=0,
        mdxc_params={'overlap':contract['overlap'],'batch_size':1,'pitch_shift':0})
    engine.load_model(FILENAME+'.ckpt')
    if str(engine.model_instance.torch_device)!='mps':raise RuntimeError('Mac GPU 대신 다른 장치가 선택됐습니다')
    return engine

def main(file):
    import numpy as np
    import soundfile as sf
    import torch
    if importlib.metadata.version('audio-separator')!='0.47.0' or torch.__version__.split('+')[0]!='2.14.1':
        raise RuntimeError('BS 음성 도구 설치.command로 고정 버전 실행기를 준비하세요')
    args=json.loads(Path(file).read_text(encoding='utf-8'));folder=Path(args['output']);contract=args['contract']
    if digest(Path(args['audio']))!=args['input_sha256']:raise ValueError('분리 입력 사본이 변경됐습니다')
    parent=os.getppid()
    def watch():
        while True:
            time.sleep(.5)
            if os.getppid()!=parent:os.kill(os.getpid(),signal.SIGTERM)
    threading.Thread(target=watch,daemon=True).start()
    started=time.monotonic();rate=44100;chunk=60*rate;context=8*rate
    engine=None;entries=[];peak=0;load_seconds=0
    with sf.SoundFile(args['audio']) as source:
        if source.samplerate!=rate or source.channels!=2:raise ValueError('BS-Roformer 입력은 44.1kHz 스테레오여야 합니다')
        frames=len(source);wav_format(frames,rate,2)
        for index,start in enumerate(range(0,frames,chunk)):
            end=min(frames,start+chunk);left=max(0,start-context);right=min(frames,end+context)
            signature={'start':start,'frames':end-start,'contract':contract}
            path=folder/f'{index:06}.npz';meta=path.with_suffix('.json')
            if path.exists()!=meta.exists():
                orphan=path if path.exists() else meta
                orphan.rename(orphan.with_name(orphan.stem+'-orphan-'+uuid.uuid4().hex+orphan.suffix))
            if path.exists() or meta.exists():
                saved=json.loads(meta.read_text(encoding='utf-8'))
                if saved.get('signature')!=signature or saved.get('sha256')!=digest(path):raise ValueError('분리 조각이 변경됐습니다')
            else:
                if engine is None:
                    load=time.monotonic();engine=load_model(Path(args['models']),folder,contract);torch.mps.synchronize();load_seconds=time.monotonic()-load
                source.seek(left);audio=source.read(right-left,dtype='float32',always_2d=True)
                # 아주 짧은 구간도 같은 창 조건에서 처리하고 원래 길이로 되돌린다.
                padded=np.pad(audio,((0,max(0,rate*8-len(audio))),(0,0)))
                result=engine.model_instance.demix(padded.T)
                target=np.asarray(result['Vocals'].T[start-left:end-left],dtype=np.float32)
                raw=audio[start-left:end-left];residual=raw-target
                if target.shape!=raw.shape or not np.isfinite(target).all() or not np.isfinite(residual).all():raise ValueError('BS-Roformer 출력 형식·수치가 잘못됐습니다')
                raw_rms=float(np.sqrt(np.mean(raw**2)));voice_rms=float(np.sqrt(np.mean(target**2)))
                review=raw_rms>.005 and voice_rms<raw_rms*.01
                with path.with_suffix('.part').open('wb') as out:np.savez(out,target=target,residual=residual)
                path.with_suffix('.part').replace(path)
                save(meta,{'signature':signature,'sha256':digest(path),'raw_rms':raw_rms,'voice_rms':voice_rms,'review':review})
                torch.mps.synchronize();peak=max(peak,torch.mps.driver_allocated_memory())
                del result,target,residual,padded,audio;torch.mps.empty_cache()
            entries.append(path)
            save(folder/'progress.json',{'processed_ms':round(end/rate*1000),'duration_ms':round(frames/rate*1000),'chunks':len(entries)})
        for name in ('target','residual'):
            pending=folder/(name+'.part.wav');written=0
            with sf.SoundFile(str(pending),'w',samplerate=rate,channels=2,subtype='FLOAT',format=wav_format(frames,rate,2)) as out:
                for path in entries:
                    with np.load(path) as data:
                        x=data[name]
                        if x.ndim!=2 or x.shape[1]!=2 or not np.isfinite(x).all():raise ValueError('저장된 분리 조각이 잘못됐습니다')
                        out.write(x);written+=len(x)
            if written!=frames:raise ValueError('분리 출력 길이가 일치하지 않습니다')
            pending.replace(folder/(name+'.wav'))
    if digest(Path(args['audio']))!=args['input_sha256']:raise ValueError('분리 중 입력 사본이 변경됐습니다')
    save(folder/'result.json',{'frames':frames,'sample_rate':rate,'channels':2,'seconds':round(time.monotonic()-started,3),
        'load_seconds':load_seconds,'device':'mps','rss_peak_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'mps_driver_observed_peak_bytes':peak,'review_chunks':[i for i,p in enumerate(entries) if json.loads(p.with_suffix('.json').read_text(encoding='utf-8')).get('review')],
        'contract':contract,'hashes':{name:digest(folder/(name+'.wav')) for name in ('target','residual')}})

if __name__=='__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    main(sys.argv[1])
