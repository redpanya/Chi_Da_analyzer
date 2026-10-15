"""긴 무음을 연결하지 않고 검출 창별 원 시각으로 전사를 합친다."""
from . import speech_media as media, speech_store as store, speech_vad, speech_options
from .storage import save_json
from .source import check_cancel


def recognize(binary, model, audio, folder, index, duration, language, vad_model, stop, lock, options=None):
    options = speech_options.validate(options)
    # 검출을 꺼도 30초 창으로 나눠 Whisper 입력과 취소·복구 비용을 제한한다.
    spans = ([[start, min(start+30000, duration)] for start in range(0, duration, 30000)]
             if options['vad'] == 'off' else speech_vad.detect(audio, vad_model, folder, index, duration, stop, lock, options['vad']))
    combined = {'transcription': [], 'windows': spans, 'reason': 'vad_no_speech' if not spans else None}
    # 세부 토큰에는 UTF-8 문자의 중간 바이트가 들어갈 수 있다. 본문·시각 JSON만 받는다.
    args = [binary,'-m',str(model),'-l',language,'-oj','-t','4','-np','-mc','0']
    if options['prompt']: args += ['--prompt', options['prompt']]
    inputs = []
    for number,(start,end) in enumerate(spans):
        check_cancel(stop)
        name = folder/f'{index:05d}-speech-{number:04d}'
        wav = name.with_suffix('.wav')
        media.chunk_audio(audio,wav,start,end)
        args += ['-f',str(wav),'-of',str(name)]
        inputs.append((wav,name.with_suffix('.json'),start,end))
    if inputs: media.process(args,folder/f'{index:05d}-engine.log',stop,lock)
    for wav,file,start,end in inputs:
        raw = store.read_engine_output(file)
        # 각 창의 패딩·형식을 먼저 검사한다. 모델 원출력 JSON은 별도로 보존한다.
        for row in store.normalize(raw,start,end,0):
            combined['transcription'].append({'offsets':{'from':row['start_ms'],'to':row['end_ms']},
                'text':row['text'],'encoding_review':row['encoding_review']})
        wav.unlink()
    save_json(folder/f'{index:05d}-raw.json',combined)
    return combined
