"""분리 계산 설정과 사용자 안내. 모델·정밀도·겹침은 기존대로 유지한다."""

PROFILES = (
    {'id': 'standard', 'label': '표준 · 기존 설정', 'ode': 'midpoint/16',
     'description': '기존과 같은 계산량입니다. 속도보다 분리 결과를 우선할 때 선택하세요. 분리 과정에서 발음이 손상될 수 있어 원음 확인이 필요합니다.'},
    {'id': 'balanced', 'label': '균형 · 약 1.7배 속도', 'ode': 'midpoint/8',
     'description': '모델 반복 계산을 절반으로 줄입니다. 표준보다 빠르지만 작은 목소리·발음·배경음 제거 결과가 달라질 수 있습니다.'},
    {'id': 'fast', 'label': '빠름 · 약 2.6배 속도', 'ode': 'euler/8',
     'description': '모델 반복 계산을 1/4로 줄입니다. 빠른 초안 확인에 적합하며, 발음 손상이나 배경음 잔류가 있으면 표준 또는 원음 전사와 비교하세요.'},
)
SPEED_NOTE = '속도는 M1 Pro 16GB의 10초 샘플 3개 실측 기준입니다(표준 약 26초 / 균형 15초 / 빠름 10초, 모델 로딩 제외). 전체 작업 시간과 정확도를 보장하지 않으며, 모델 크기·메모리 사용량은 거의 같습니다.'


def profile(value='standard'):
    for item in PROFILES:
        if value == item['id']: return item
    raise ValueError('음성 분리 설정은 표준·균형·빠름 중 선택하세요')


def input_kind(value):
    if value not in ('sam', 'roformer', 'original'):
        raise ValueError('전사 입력은 BS-Roformer·SAM 분리음 또는 원본 오디오를 선택하세요')
    return value


def ode_options(contract):
    ode = contract.get('ode')
    if ode not in [item['ode'] for item in PROFILES]:
        raise ValueError('지원하지 않는 SAM 계산 설정입니다')
    method, steps = ode.split('/')
    return {'method': method, 'step_size': 1 / int(steps)}


def label(value):
    return profile(value)['label'].split(' · ')[0]
