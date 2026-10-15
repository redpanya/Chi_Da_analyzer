"""발화 검출과 원 시각을 보존하는 전사 창. 모델·출력은 원자적으로 저장한다."""
from pathlib import Path
import sys
from urllib.request import urlopen
from . import model_paths, speech_model, speech_media, voice_models
from .source import check_cancel
from .storage import ProjectLock, save_json, read_json

SHA256 = '9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6'
SIZE = 643854
URL = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx'
REVISION = 1
COVERAGE_REVISION = 1


def coverage(spans, duration, offset=0, digital_silence=False):
    """인식 호출 범위와 호출하지 않은 범위를 구분한다. VAD 미검출은 무음 확정이 아니다."""
    cursor=0; skipped=[]
    for start,end in spans:
        if not 0<=cursor<=start<end<=duration:raise ValueError('인식 처리 범위가 올바르지 않습니다')
        if cursor<start:skipped.append([offset+cursor,offset+start])
        cursor=end
    if cursor<duration:skipped.append([offset+cursor,offset+duration])
    return {'revision':COVERAGE_REVISION,'asr_windows':[[offset+a,offset+b] for a,b in spans],
            'not_transcribed':skipped,'reason':'digital_silence' if digital_silence else 'vad_not_detected',
            'digital_silence_candidate':bool(digital_silence),
            'speech_absence_confirmed':False,'asr_confidence':'not_collected'}


def prepare(stop, update):
    if not voice_models.PYTHON.is_file(): raise ValueError('발화 검출용 음성 실행 도구를 먼저 설치하세요')
    folder = model_paths.available()
    target = folder/'silero-vad.onnx'
    with ProjectLock(folder):
        if target.is_symlink(): raise ValueError('발화 모델의 연결 파일은 지원하지 않습니다')
        if target.is_file() and speech_model.digest(target, stop) == SHA256: return target
        if target.exists(): raise ValueError('발화 검출 모델이 손상됐습니다. 기존 파일을 별도 보관한 뒤 다시 준비하세요')
        update(message='발화 검출 모델 준비 · 약 644KB')
        part = target.with_suffix('.download')
        if part.is_symlink(): raise ValueError('발화 모델 임시 파일의 연결은 지원하지 않습니다')
        with urlopen(URL, timeout=30) as response, part.open('wb') as output:
            total = 0
            while block := response.read(65536):
                check_cancel(stop); total += len(block)
                if total > SIZE: raise ValueError('발화 모델 크기가 예상과 다릅니다')
                output.write(block)
        if total != SIZE or speech_model.digest(part, stop) != SHA256: raise ValueError('발화 모델 해시 검사 실패')
        check_cancel(stop); part.replace(target)
    return target


def windows(spans, duration):
    result = []; previous = 0
    for span in spans:
        if (not isinstance(span,list) or len(span)!=2 or any(type(x) is not int for x in span)
                or not previous <= span[0] < span[1] <= duration):
            raise ValueError('발화 검출 시각이 입력 범위를 벗어났습니다')
        a, b = span; previous = b
        a, b = max(0,a-250), min(duration,b+1000)
        if result and (a <= result[-1][1] or (a-result[-1][1] <= 2000 and b-result[-1][0] <= 30000)):
            result[-1][1] = max(result[-1][1],b)
        else: result.append([a,b])
    return result


def detect(audio, model, folder, index, duration, stop, lock, mode='standard'):
    from .speech_options import validate
    validate({'vad':mode})
    request = folder/f'{index:05d}-vad-request.json'
    output = folder/f'{index:05d}-vad.json'
    save_json(request, {'action':'vad','audio':str(audio),'model':str(model),'output':str(output),'vad_mode':mode})
    entry = '--voice-worker' if getattr(sys,'frozen',False) else str(Path(__file__).resolve().parents[1]/'workers/voices.py')
    speech_media.process([str(voice_models.PYTHON),entry,str(request)],folder/f'{index:05d}-vad.log',stop,lock)
    spans=windows(read_json(output)['segments'], duration)
    save_json(folder/f'{index:05d}-vad-coverage.json',coverage(spans,duration))
    return spans
