"""개정 4의 결과를 건드리지 않고 호환되는 구조·요약만 새 실행으로 복사한다."""
import uuid
from .context_job import local
from .context_hierarchy import REVISION
from .storage import read_json,save_json,stamp


def fork(job,saved,source):
    old=saved['id'];id=uuid.uuid4().hex
    origin=local(job.path,f'runs/{old}');folder=local(job.path,f'runs/{id}')
    # 지시문·스키마가 바뀌지 않은 체크포인트만 복사한다. 재사용 시 기존 서명 검사를 다시 통과해야 한다.
    for file in origin.glob('*.json'):
        name=file.name
        if name=='outline.json' or name.startswith(('map-','boundary-','short-','parent-','summary-')):
            value=read_json(local(job.path,f'runs/{old}/{name}'));save_json(folder/name,value)
    timeline=origin/'timeline.json'
    if timeline.exists():
        value=read_json(local(job.path,f'runs/{old}/timeline.json'))
        items=[{k:v for k,v in item.items() if k!='reactions'} for item in value['items'] if item['kind'] in ('story','topic')]
        save_json(folder/'timeline.json',{'items':items,'done':len(items),'active':None})
    result=saved|{'id':id,'recovered_from':old,'pipeline_revision':REVISION,'complete':False,
                  'reaction_failures':0,'created_at':stamp(),'updated_at':stamp()}
    save_json(folder/'source.json',source);save_json(folder/'result.json',result)
    job.update(run=id,full_run=id,runs=job.value['runs']+[{'id':id,'scope':'full','label':'전체 영상 · 복구 버전','title':stamp()}])
    return result
