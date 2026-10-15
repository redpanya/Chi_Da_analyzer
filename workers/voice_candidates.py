"""선택한 구간만 읽어 목소리 특징을 비교한다. 점수는 동일인 확률이 아니다."""
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time
import numpy as np
import soundfile as sf
import sherpa_onnx as sherpa


def compare(request):
    config=sherpa.SpeakerEmbeddingExtractorConfig(model=request['model'],num_threads=4,provider='cpu')
    if not config.validate():raise ValueError('음향 비교 모델 구성 오류')
    extractor=sherpa.SpeakerEmbeddingExtractor(config)
    with sf.SoundFile(request['audio']) as source:
        rate=source.samplerate
        if rate!=16000 or source.channels!=1:raise ValueError('음향 비교 입력은 16kHz 모노여야 합니다')
        def vector(row):
            start=round(row['start_ms']*rate/1000);end=min(len(source),round(row['end_ms']*rate/1000),start+10*rate)
            if start<0 or end-start<rate:return None
            source.seek(start);samples=source.read(end-start,dtype='float32')
            if not np.isfinite(samples).all() or float(np.sqrt(np.mean(samples**2)))<.001:return None
            stream=extractor.create_stream();stream.accept_waveform(rate,samples);stream.input_finished()
            if not extractor.is_ready(stream):return None
            v=np.asarray(extractor.compute(stream),dtype='float32');norm=np.linalg.norm(v)
            return v/norm if np.isfinite(v).all() and norm>1e-8 else None
        refs={}
        for row in request['references']:
            v=vector(row)
            if v is not None:refs.setdefault(row['speaker'],[]).append((v,row))
        output={}
        for row in request['rows']:
            v=vector(row);scores=[]
            if v is not None:
                for speaker,samples in refs.items():
                    scores.append({'speaker':speaker,'similarity':round(float(np.mean([np.dot(v,w) for w,_ in samples])),4),
                                   'samples':[r for _,r in samples]})
            scores.sort(key=lambda r:r['similarity'],reverse=True)
            # 순위만 제시한다. 검증되지 않은 임계값이나 동일인 확률을 만들지 않는다.
            output[row['id']]={'candidates':scores[:3], 'note':'최대 첫 10초의 코사인 유사도 순위 · 동일인 확률 아님. 중첩 음성은 잘못 연결될 수 있습니다.' if scores else
                              '음향 근거 부족 · 짧거나 조용한 발언 또는 비교할 단독 대표 음성 없음'}
    return output


def main(file):
    parent=os.getppid()
    def watch():
        while True:
            time.sleep(.5)
            if os.getppid()!=parent:os.kill(os.getpid(),signal.SIGTERM)
    threading.Thread(target=watch,daemon=True).start()
    request=json.loads(Path(file).read_text(encoding='utf-8'))
    Path(request['output']).write_text(json.dumps(compare(request),ensure_ascii=False),encoding='utf-8')


if __name__=='__main__':main(sys.argv[1])
