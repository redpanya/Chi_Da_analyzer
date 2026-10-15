"""형식 6: 단일 문맥과 통계 반응. 응답 실패는 구간별로 보존하고 계속한다."""
import uuid
from . import context_input as inputs, context_flat_model as model, context_evidence as ev, analysis
from .context_job import local
from .source import check_cancel
from .storage import read_json,save_json,stamp


def failed(value,error):
    return {'start_ms':value['range']['start_ms'],'end_ms':value['range']['end_ms'],
            'failed':True,'error':str(error),'input':value,'range_sources':True,
            'summary':{'title':'문맥 정리 실패 · 확인 필요','context':[],'chat':[],'relation':[],'uncertainties':[]}}


def process(job,saved,source):
    folder=local(job.path,f"runs/{saved['id']}")
    ranges=folder/'reaction-ranges.json'
    if not ranges.exists():
        check_cancel(job.stop)
        save_json(ranges,analysis.analyze(source['chat'],source['duration_ms'],'전체 제공 채팅' in source['notes'],saved['reaction_settings']))
    timeline_file=folder/'timeline.json'
    visible_done=read_json(timeline_file)['done'] if timeline_file.exists() else 0
    items=[];boundaries=[];errors=0
    for index,chunk in enumerate(saved['chunks']):
        check_cancel(job.stop)
        progress={'stage':'flat','done':index,'total':len(saved['chunks']),'processed_ms':chunk['range']['start_ms'],
                  'duration_ms':saved['duration_ms'],'seconds':0}
        job.update(message=f"문맥 정리 · {chunk['label']}",progress=progress)
        if chunk['state'] in ('complete','gap'):
            data=read_json(folder/chunk['file'])
        else:
            value=inputs.window(source,chunk['range'],whole=True)
            for row in value['evidence']:row['id']=row['id'][0]+str(index)+'_'+row['id'][1:]
            if not any(r['kind']=='speech' for r in value['evidence']):
                current=[{'start_ms':chunk['range']['start_ms'],'end_ms':chunk['range']['end_ms'],'gap':True}];state='gap'
            else:
                try:current=model.summarize(job,folder,f'flat-{index}',value);state='complete'
                except ev.ModelResponseError as error:current=[failed(value,error)];state='failed'
            current=[row|{'id':f"flat-{row['start_ms']}",'input':value} for row in current]
            data={'input':value,'items':current,'seconds':0}
            check_cancel(job.stop)
            file=f'chunk-{index}-{uuid.uuid4().hex}.json';save_json(folder/file,data)
            chunk.update(state=state,file=file);save_json(folder/'result.json',saved)
        current=list(data['items']);errors+=sum(bool(row.get('failed')) for row in current)
        if items and not any(row.get('gap') or row.get('failed') for row in (items[-1],current[0])):
            job.update(message=f"앞뒤 문맥 연결 확인 · {chunk['label']}",progress=progress)
            try:
                joined=model.join(job,folder,items[-1],current[0])
                if joined:items[-1]=joined;current=current[1:]
            except ev.ModelResponseError as error:
                current[0]=current[0]|{'boundary_error':str(error)};boundaries.append(index)
        check_cancel(job.stop);items.extend(current)
        timeline={'done':index+1,'items':items,'seconds':0,'boundary_failures':boundaries,'item_failures':errors}
        # 재검토 도중 중단해도 뒤쪽의 기존 완료 목록을 잃지 않는다.
        if index+1>=visible_done:save_json(timeline_file,timeline)
        job.update(progress=progress|{'done':index+1,'processed_ms':chunk['range']['end_ms']})
    from .context_full import current_source,fingerprint
    if fingerprint(current_source(job.path,job.vod,source['chat_offset_ms']))!=saved['fingerprint']:
        raise ValueError('처리 중 입력이 바뀌었습니다. 완료 부분은 보존합니다. 새 정리를 시작하세요')
    check_cancel(job.stop)
    failures=errors+len(boundaries)
    saved.update(complete=not failures,item_failures=errors,boundary_failures=len(boundaries),updated_at=stamp())
    save_json(folder/'result.json',saved)
    return failures
