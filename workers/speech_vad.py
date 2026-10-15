"""설치된 sherpa-onnx로 짧은 PCM 조각의 발화 시각만 검출한다."""
import sherpa_onnx as sherpa
import soundfile as sf


def detect(request):
    audio, rate = sf.read(request['audio'], dtype='float32')
    if rate != 16000 or audio.ndim != 1 or len(audio) > rate*300:
        raise ValueError('발화 검출 입력은 최대 5분의 16kHz 모노여야 합니다')
    mode = request.get('vad_mode', 'standard')
    if mode not in ('standard', 'sensitive'): raise ValueError('발화 검출 설정이 올바르지 않습니다')
    threshold, minimum = (.2, .15) if mode == 'sensitive' else (.35, .25)
    config = sherpa.VadModelConfig(
        silero_vad=sherpa.SileroVadModelConfig(model=request['model'], threshold=threshold,
            min_silence_duration=.3, min_speech_duration=minimum, max_speech_duration=30),
        sample_rate=rate, num_threads=1, provider='cpu')
    vad = sherpa.VoiceActivityDetector(config, buffer_size_in_seconds=310)
    spans = []
    def drain():
        while not vad.empty():
            item = vad.front
            spans.append([round(item.start*1000/rate), min(round((item.start+len(item.samples))*1000/rate), round(len(audio)*1000/rate))])
            vad.pop()
    for start in range(0, len(audio), 512):
        vad.accept_waveform(audio[start:start+512]); drain()
    vad.flush(); drain()
    return {'segments': spans, 'engine': 'sherpa-onnx '+sherpa.__version__}
