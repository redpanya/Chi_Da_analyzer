"""별도 설치하는 sherpa 실행기. 발화 검출·화자 후보 비교도 같은 엔진을 사용한다."""
from pathlib import Path
import sys

if not getattr(sys, 'frozen', False): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def check():
    import numpy
    import soundfile
    import sherpa_onnx
    from workers import voices, speech_vad, voice_candidates
    print('CHIDA_SPEAKER_TOOL:1:sherpa', flush=True)


def main():
    if sys.argv[1:] == ['--speaker-tool-check']: return check()
    if len(sys.argv) != 3: raise ValueError('화자 실행 요청을 확인하세요')
    if sys.argv[1] == '--voice-worker':
        from workers.voices import main as run
    elif sys.argv[1] == '--voice-candidate-worker':
        from workers.voice_candidates import main as run
    else: raise ValueError('지원하지 않는 화자 실행 요청입니다')
    run(sys.argv[2])


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    main()
