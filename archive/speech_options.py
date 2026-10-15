"""전사 설정 검증과 실행 지문. 기존 전사·수동 교정에는 쓰지 않는다."""
VAD = {'standard': {'threshold': .35, 'min_speech_duration': .25},
       'sensitive': {'threshold': .2, 'min_speech_duration': .15}, 'off': None}
REVISION = 1


def validate(value=None):
    if value is None: value = {}
    if not isinstance(value, dict) or set(value) - {'vad', 'prompt'}:
        raise ValueError('전사 옵션 형식이 올바르지 않습니다')
    vad, prompt = value.get('vad', 'standard'), value.get('prompt', '')
    if not isinstance(vad, str) or vad not in VAD:
        raise ValueError('발화 검출은 표준·민감·끄기 중에서 선택하세요')
    if not isinstance(prompt, str) or len(prompt) > 500 or any(ord(c) < 32 and c not in '\n\t' for c in prompt):
        raise ValueError('용어 힌트는 제어 문자 없이 500자 이내로 입력하세요')
    return {'vad': vad, 'prompt': prompt.strip()}
