"""선택 단계와 구버전 진행 범위를 같은 실행 순서로 해석한다."""
from . import automation_summary

STEPS = ('download', 'audio', 'transcribe', 'diarize', 'context')


def selected(value):
    if 'steps' not in value:
        return (['download', 'audio', 'transcribe']
                + (['diarize'] if value.get('speakers_enabled') else []) + ['context']
                if value.get('mode') == 'analysis' else ['download'])
    result = value['steps']
    if (not isinstance(result, list) or not result or len(result) > len(STEPS)
            or any(not isinstance(step, str) or step not in STEPS for step in result)
            or len(set(result)) != len(result)):
        raise ValueError('진행할 단계를 하나 이상 선택하세요. 중복되거나 알 수 없는 단계는 사용할 수 없습니다')
    return [step for step in STEPS if step in result]


def sequence(value):
    chosen = selected(value)
    result = [step for step in chosen if step != 'context']
    if 'context' in chosen:
        modes = automation_summary.validate(value.get('summary_modes', ['detail']))
        result += ['reactions'] + [automation_summary.STAGES[mode] for mode in modes]
    return result
