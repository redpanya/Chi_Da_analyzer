"""Community-1 전용 환경. 인증은 HF 로컬 저장소에서 읽고 작업 파일에 저장하지 않는다."""
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time
import traceback

ROOT=Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]
if not getattr(sys,'frozen',False): sys.path.insert(0,str(ROOT))
os.environ['PYANNOTE_METRICS_ENABLED']='0'
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
os.environ.setdefault('MPLCONFIGDIR',str(Path.home()/'Library/Caches/chzzk-archive-tools/pyannote/matplotlib'))

from archive.storage import save_json


def run(request):
    folder=Path(request['output']).parent
    def progress(**value): save_json(folder/'progress.json',value)
    if request['action']=='prepare':
        from huggingface_hub import get_token, snapshot_download
        if not get_token(): raise ValueError('HF_AUTH_REQUIRED')
        spec=json.loads((ROOT/'archive/diarization_catalog.json').read_text(encoding='utf-8'))['pyannote']
        target=Path(request['model_root'])/'voices/pyannote'/spec['revision']
        snapshot_download(spec['repo'],revision=spec['revision'],local_dir=target,allow_patterns=[f['name'] for f in spec['files']])
        return {'prepared':True}
    os.environ['HF_HUB_OFFLINE']='1'
    import torch
    import soundfile as sf
    from pyannote.audio import Pipeline
    from archive.audio_limits import MAX_MS
    torch.set_num_threads(4)
    with sf.SoundFile(request['audio']) as file:
        if file.samplerate!=16000 or file.channels!=1 or len(file)*1000>MAX_MS*16000:
            raise ValueError('화자 입력은 최대 20시간의 16kHz 모노여야 합니다')
    device='mps' if torch.backends.mps.is_available() else 'cpu'
    progress(phase='모델 로드',device=device)
    engine=Pipeline.from_pretrained(request['cache'])
    engine.to(torch.device(device))
    audio,rate=sf.read(request['audio'],dtype='float32')
    def hook(step_name,step_artifact=None,**kwargs):
        names={'segmentation':'발화 구간 탐지','embeddings':'목소리 특징 추출','clustering':'화자 연결','discrete_diarization':'화자 배정','speaker_counting':'화자 수 추정'}
        progress(phase=names.get(step_name,'화자 분석'),completed=int(kwargs.get('completed') or 0),total=int(kwargs.get('total') or 0))
    options={'num_speakers':request['speakers']} if request['speakers']>0 else {}
    result=engine({'waveform':torch.from_numpy(audio).unsqueeze(0),'sample_rate':rate},hook=hook,**options)
    labels={}; turns=[]
    for turn,_,label in result.speaker_diarization.itertracks(yield_label=True):
        if label not in labels: labels[label]=len(labels)
        a,b=round(turn.start*1000),round(turn.end*1000)
        if a<b: turns.append({'start_ms':a,'end_ms':b,'speaker':labels[label]})
    return {'turns':turns,'engine':'pyannote.audio 4.0.7 · Community-1','device':device,'requested_speakers':request['speakers']}


def main():
    if sys.argv[1:] == ['--speaker-tool-check']:
        import torch
        import soundfile
        from pyannote.audio import Pipeline
        print('CHIDA_SPEAKER_TOOL:1:pyannote',flush=True)
        return
    request=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    parent=os.getppid()
    def watch():
        while True:
            time.sleep(.5)
            if os.getppid()!=parent: os.kill(os.getpid(),signal.SIGTERM)
    threading.Thread(target=watch,daemon=True).start()
    began=time.monotonic()
    try:
        result=run(request)
        save_json(Path(request['output']),result|{'elapsed_seconds':round(time.monotonic()-began,3)})
    except Exception as error:
        # 인증 예외의 요청 헤더·토큰을 로그에 직렬화하지 않는다.
        name=type(error).__name__
        auth='GatedRepo' in name or 'HF_AUTH_REQUIRED' in str(error) or getattr(getattr(error,'response',None),'status_code',0) in (401,403)
        message='Community-1 이용 동의 후 전용 hf auth login으로 로그인하세요.' if auth else f'Community-1 처리 실패 ({name}): '+str(error)[:500]
        save_json(Path(request['output']).parent/'error.json',{'message':message})
        print(message,file=sys.stderr)
        if request['action']!='prepare':
            print(''.join(traceback.format_tb(error.__traceback__)),file=sys.stderr)
        raise SystemExit(1)


if __name__=='__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    main()
