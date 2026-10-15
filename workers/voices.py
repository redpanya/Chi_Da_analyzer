"""별도 가상환경에서만 로드하는 CPU 화자 구분·음원 분리 엔진."""
import json
from pathlib import Path
import sys
import time
import os
import signal
import threading

if not getattr(sys, 'frozen', False):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from archive.audio_limits import MAX_MS
from workers import diarization_long

import numpy as np
import soundfile as sf


def diarize(request):
    import sherpa_onnx as sherpa
    cache = Path(request['cache'])
    config = sherpa.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(cache/'segmentation.onnx')),
            num_threads=4, provider='cpu'),
        embedding=sherpa.SpeakerEmbeddingExtractorConfig(model=str(cache/'embedding.onnx'), num_threads=4, provider='cpu'),
        clustering=sherpa.FastClusteringConfig(num_clusters=request['speakers'], threshold=.9),
        min_duration_on=.3, min_duration_off=.5)
    if not config.validate():
        raise ValueError('화자 모델 구성 검사 실패')
    engine = sherpa.OfflineSpeakerDiarization(config)
    with sf.SoundFile(request['audio']) as source:
        rate=source.samplerate
        if rate!=16000 or source.channels!=1 or len(source)*1000>MAX_MS*rate:
            raise ValueError('화자 입력은 최대 20시간의 16kHz 모노여야 합니다')
        long=len(source)>diarization_long.CHUNK_SECONDS*rate
    if long:
        request['signature']=request['signature']|{'engine':'sherpa-onnx '+sherpa.__version__}
        config.clustering.num_clusters=-1;engine.set_config(config)
        extractor=sherpa.SpeakerEmbeddingExtractor(config.embedding)
        def cluster(features, requested):
            if len(features)==1:return [0]
            return sherpa.FastClustering(sherpa.FastClusteringConfig(num_clusters=min(requested,len(features)) if requested>0 else -1,threshold=.9))(features)
        result=diarization_long.run(request,engine,extractor,cluster,seconds=diarization_long.CHUNK_SECONDS)
        return result|{'engine':'sherpa-onnx '+sherpa.__version__}
    audio, rate = sf.read(request['audio'], dtype='float32')
    if rate != 16000 or audio.ndim != 1:
        raise ValueError('화자 입력은 16kHz 모노여야 합니다')
    def progress(done, total):
        print(json.dumps({'processed': done, 'total': total}), flush=True)
        return 0
    turns = engine.process(audio, callback=progress).sort_by_start_time()
    return {'turns': [{'start_ms': round(t.start*1000), 'end_ms': round(t.end*1000), 'speaker': int(t.speaker)} for t in turns],
            'engine': 'sherpa-onnx '+sherpa.__version__, 'threshold': .9, 'requested_speakers': request['speakers']}


def main(file):
    request = json.loads(Path(file).read_text(encoding='utf-8'))
    parent=os.getppid()
    def watch():
        while True:
            time.sleep(.5)
            if os.getppid()!=parent:os.kill(os.getpid(),signal.SIGTERM)
    threading.Thread(target=watch,daemon=True).start()
    began = time.monotonic()
    if request['action'] == 'vad':
        from workers.speech_vad import detect
        result = detect(request)
    elif request['action'] == 'diarize': result = diarize(request)
    else: raise ValueError('지원하지 않는 음성 작업입니다')
    result['elapsed_seconds'] = round(time.monotonic()-began, 3)
    Path(request['output']).write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main(sys.argv[1])
