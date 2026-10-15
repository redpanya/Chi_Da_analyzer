"""분리 실행기와 GUI가 공유하는 고정 모델·설정. 외부 의존성 없음."""
NAME = 'BS-Roformer-Viperx-1297'
REVISION = 'uvr-3826b05b'
FILENAME = 'model_bs_roformer_ep_317_sdr_12.9755'
FILES = (
    (FILENAME+'.ckpt', 639331213, '5b84f37e8d444c8cb30c79d77f613a41c05868ff9c9ac6c7049c00aefae115aa',
     'https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/'+FILENAME+'.ckpt'),
    (FILENAME+'.yaml', 2273, '2bfdd16c656bd9519aba757cc4f8834b7ede675eb1e00ec4772d74ae1c41af7f',
     'https://raw.githubusercontent.com/TRvlvr/application_data/3826b05b570dbd4fbedbc807758803b35348ba1b/mdx_model_data/mdx_c_configs/'+FILENAME+'.yaml'),
)
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

