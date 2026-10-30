"""출력 비트레이트는 가변적이다. 예상 범위와 실제 남은 공간을 분리한다."""
import shutil
from pathlib import Path

RESERVE=256*1024**2

def estimate(src,request,caption_count=0):
    seconds=sum(c['end_ms']-c['start_ms'] for c in request['clips'])/1000
    rate=Path(src['file']).stat().st_size/max(1,src['duration']/1000)
    fast=request['options']['speed']=='fast'
    lower=seconds*(rate if fast else max(32000,rate*.5))
    upper=seconds*(rate*1.2 if fast else max(1500000,rate*3))
    copies=3 if request['options']['mode']=='joined' else 2
    decorated=request['options']['caption'] or request['options'].get('image')
    if decorated:copies+=1
    return {'output_min':round(lower),'output_max':round(upper),'required_min':round(lower*copies)+RESERVE,
            'required_max':round(upper*copies)+RESERVE+max(1,caption_count)*src['width']*src['height']*4 if decorated else round(upper*copies)+RESERVE}

def available(folder,minimum=RESERVE):
    free=shutil.disk_usage(folder).free
    if free<minimum:raise ValueError(f'저장 공간이 부족합니다. 필요 최소 약 {minimum/1024**3:.2f}GiB / 남은 공간 {free/1024**3:.2f}GiB. 완료 파일을 보존했습니다')
    return free

def preflight(folder,src,request,caption_count=0):
    value=estimate(src,request,caption_count);value.update(folder=str(folder),free=shutil.disk_usage(folder).free)
    value['enough']=value['free']>=value['required_min'];return value
