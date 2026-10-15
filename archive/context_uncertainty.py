"""새 요약에만 적용하는 내용 중심 입력. 이전 실행의 프롬프트는 유지한다."""
from . import context_dialogue_input as di, context_dialogue_model as model
from .context_flat_model import POLICY

VERSION = 1


def rows(source):
    original = {r.get('id', str(i)): r for i, r in enumerate(source['speech'])}
    result = di.rows(source)
    for row in result:
        source_row = original[row['source_id']]
        status = source_row.get('status', 'unassigned')
        tag = row['speaker_tag']
        row['speaker_tag'] = ('화자 불명·'+row['id'] if tag == '?' or status == 'failed' else
                              ('확인 ' if status == 'confirmed' else '추정 ')+tag)
    return result


def dialogue_prompt(rows, active):
    # 기존 응답 구조·범위 검사는 공유하고 의미 규칙만 새 실행에서 강화한다.
    base = model.dialogue_prompt(rows, active)
    policy = ('\n화자 배정이 불완전한 다인 방송이다. 내용을 이해할 수 있으면 화자 불명이어도 요약한다. '
              '불명 태그의 발언들은 같은 사람인지 다른 사람인지 모른다. 추정 태그도 오배정될 수 있다. '
              '인물 귀속이 불확실하면 이름 없이 사건·질문·의견 차이를 정리한다. 반대 의견을 한 사람의 변심이나 전체 합의로 바꾸지 않는다. '
              '질문·답변·인용·성대모사·게임/후원 음성을 실제 방송자의 신원으로 연결하지 않는다. '
              '내용 자체가 누락·모순되면 확인 가능한 부분만 쓰고 결말·대사를 만들어 채우지 않는다. '
              '화자 불명 설명으로 요약을 대체하지 않는다. 주체 불확실성 때문에 사건 해석이 달라지는 경우에만 짧게 명시한다. '
              '화자 태그를 제목·본문에 노출하지 않는다.')
    return base.replace(POLICY, POLICY+policy, 1)
