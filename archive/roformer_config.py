"""기존 BS-Roformer 결과에 저장된 모델·프로필 이름을 표시한다."""
NAME = 'BS-Roformer-Viperx-1297'
PROFILES = (
    {'id':'standard', 'label':'표준 · FP32 / 겹침 4', 'overlap':4, 'fp16':False,
     'description':'원래 정밀도와 75% 겹침을 사용합니다. 계산량이 많아 음원 길이보다 오래 걸릴 수 있습니다.'},
    {'id':'fast', 'label':'빠름 · FP16 / 겹침 2', 'overlap':2, 'fp16':True,
     'description':'50% 겹침과 낮은 정밀도로 계산량을 줄입니다. 작은 목소리·경계 발음이 달라질 수 있어 원음과 비교하세요.'},
)

def profile(value='fast'):
    for item in PROFILES:
        if value == item['id']: return item
    raise ValueError('BS-Roformer 설정은 표준 또는 빠름을 선택하세요')

