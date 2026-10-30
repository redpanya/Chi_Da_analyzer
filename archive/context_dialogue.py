"""형식 7: 대사 중심 단일 문맥, 독립 채팅 후처리와 원자적 복구 상태."""
from . import error_log
import copy
from . import analysis, context_evidence as ev, context_dialogue_input as di
from . import context_dialogue_model as model, context_tokens as tokens
from .context_job import local
from .source import check_cancel
from .storage import read_json, save_json, stamp

REVISION=1


def failed(source, rows, error):
    item=di.card(source,rows,'요약 실패','이 범위의 요약을 확인하지 못했습니다.')
    return item|{'failed':True,'error':str(error),'chat_state':'skipped'}


def publish(folder, state):
    save_json(folder/'dialogue-state.json',state)


def close(state, following=None):
    if state['active']:
        state['items'].append(di.close(state['active'],following))
        state['active']=None


def gaps(source, state):
    """문맥 밖의 전사 없는 시간은 채팅 관측 대상으로만 남긴다."""
    end=0;result=[]
    for item in sorted(state['items'],key=lambda r:r['start_ms']):
        if item['start_ms']-end>=di.GAP_MS:result.append((end,item['start_ms']))
        end=max(end,item['end_ms'])
    if source['duration_ms']-end>=di.GAP_MS:result.append((end,source['duration_ms']))
    for start,end in result:
        value=di.value(source,[],start,end,1600)
        state['items'].append({'id':f'gap-{start}','start_ms':start,'end_ms':end,'gap':True,'input':value,
            'summary':{'title':'사용 가능한 전사 없음','context':[],'chat':[],'relation':[],'uncertainties':[]},'chat_state':'pending'})
    state['items'].sort(key=lambda r:r['start_ms'])


def apply(source, rows, raw, state):
    ids=[r['id'] for r in rows]
    for index,part in enumerate(raw['topics']):
        selected=rows[ids.index(part['start_id']):ids.index(part['end_id'])+1]
        try:
            title=ev.text(part['title'],80);text=ev.text(part['context'],360)
            if any(r.get('time_review') for r in selected):raise ValueError('전사 시각이 영상 범위를 벗어나거나 유효하지 않습니다')
        except (ValueError,TypeError) as error:
            close(state,selected[0]);state['items'].append(failed(source,selected,error));continue
        if index==0 and raw['continues'] and state['active']:
            selected=[r for r in state['active']['input']['evidence'] if r['kind']=='speech']+selected
        else:close(state,selected[0])
        item=di.card(source,selected,title,text)
        item['provisional']=True
        state['active']=item


def chat(job, folder, source, state, policy=None):
    pending=[]
    for item in state['items']:
        if item.get('failed') or item.get('chat_state')=='complete':continue
        selected=[r for r in item['input']['evidence'] if r['kind']=='speech']
        item['input']=di.value(source,selected,item['start_ms'],item['end_ms'],1600)
        if not any(r['kind']=='chat' for r in item['input']['evidence']):item['chat_state']='complete';continue
        pending.append(item)
    publish(folder,state)
    total=len(pending);done=0
    while pending:
        check_cancel(job.stop)
        fit_error=None
        try:group=(policy.fit if policy else tokens.fit)(pending,model.chat_prompt,job.tokenizer)
        except model.SplitRequired as error:
            if not policy:raise
            group=pending[:1];fit_error=error
        job.update(message='채팅 설명 정리 · 완료 대화는 선택·복사할 수 있습니다',
                   progress={'stage':'dialogue-chat','done':done,'total':total,'seconds':0})
        try:
            if fit_error:raise fit_error
            raw=model.call(job,folder,'chat',{'items':group},model.chat_prompt(group),model.chat_schema(group),lambda raw:model.validate_chat(raw,group))
            found={r['id']:r for r in raw['items']}
            for item in group:
                row=found.get(item['id'])
                if not row or any(not isinstance(row[k],str) or len(row[k])>limit for k,limit in [('chat',240),('relation',160)]):
                    item.update(chat_state='failed',chat_error='이 문맥의 채팅 설명이 누락되었거나 형식이 올바르지 않습니다');continue
                refs=[r['id'] for r in item['input']['evidence'] if r['kind']=='chat'][:4]
                speech=[r['id'] for r in item['input']['evidence'] if r['kind']=='speech'][:2]
                item['summary']['chat']=[{'text':row['chat'],'evidence':refs}] if row['chat'].strip() else []
                item['summary']['relation']=[{'text':row['relation'],'evidence':speech+refs[:2]}] if row['relation'].strip() and speech else []
                item['chat_state']='complete';item.pop('chat_error',None)
        except (ev.ModelResponseError,model.SplitRequired) as error:
            error_log.record('context-chat-partial',error,path=job.path)
            for item in group:item.update(chat_state='failed',chat_error=str(error))
        check_cancel(job.stop)
        pending=pending[len(group):];done+=len(group)
        publish(folder,state)
        job.update(progress={'stage':'dialogue-chat','done':done,'total':total,'seconds':0})


def process(job, saved, source, policy=None):
    from . import context_uncertainty
    content_first=bool(saved.get('speaker_policy'))
    row_builder=policy.rows if policy else context_uncertainty.rows if content_first else di.rows
    make_prompt=context_uncertainty.dialogue_prompt if content_first else model.dialogue_prompt
    folder=local(job.path,f"runs/{saved['id']}")
    mapping=folder/'utterances.json'
    if not mapping.exists():save_json(mapping,{'fingerprint':saved['fingerprint'],'rows':row_builder(source)})
    mapped=read_json(mapping)
    if mapped['fingerprint']!=saved['fingerprint']:raise ValueError('발언 대응표와 입력 지문이 다릅니다')
    rows=mapped['rows']
    ranges=folder/'reaction-ranges.json'
    if not ranges.exists():save_json(ranges,analysis.analyze(source['chat'],source['duration_ms'],'전체 제공 채팅' in source['notes'],saved['reaction_settings']))
    state_file=folder/'dialogue-state.json'
    state=read_json(state_file) if state_file.exists() else {'cursor':0,'items':[],'active':None,'phase':'dialogue','batches':0,'consecutive_failures':0}
    publish(folder,state)
    job.tokenizer=job.make_tokenizer()
    budget_end=0
    while state['cursor']<len(rows):
        check_cancel(job.stop)
        cursor=state['cursor'];before=copy.deepcopy(state)
        plan_error=None
        if policy:
            try:
                limit=budget_end-cursor if saved['version']==10 and cursor<budget_end else None
                planned=policy.plan(rows[cursor:],state['active'],job.tokenizer,limit=limit);group=planned['rows']
            except model.SplitRequired as error:group=rows[cursor:cursor+1];plan_error=error
        else:group=tokens.fit(rows[cursor:],lambda r:make_prompt(r,state['active']),job.tokenizer)
        if saved['version']==10 and cursor>=budget_end:
            job.request_budget=10;budget_end=cursor+len(group)
        while True:
            job.update(message=f"대화 문맥 정리 · {ev.inputs.clock(group[-1]['end_ms'])}까지 읽기",
                progress={'stage':'dialogue','done':cursor,'total':len(rows),'processed_ms':group[0]['start_ms'],'duration_ms':source['duration_ms'],'seconds':0})
            try:
                if plan_error:raise plan_error
                if policy:policy.infer(job,folder,planned,state)
                else:
                    raw=model.call(job,folder,'dialogue',{'rows':group,'active':state['active']},make_prompt(group,state['active']),model.dialogue_schema(group,state['active']),
                                   lambda raw:model.validate_dialogue(raw,group,state['active']))
                    apply(source,group,raw,state)
                state['consecutive_failures']=0
                break
            except model.SplitRequired:
                if len(group)>1:
                    group=group[:max(1,len(group)//2)]
                    if policy:
                        try:planned=policy.plan(rows[cursor:],state['active'],job.tokenizer,limit=len(group));group=planned['rows'];plan_error=None
                        except model.SplitRequired as error:group=rows[cursor:cursor+1];plan_error=error
                    continue
                error=ev.ModelResponseError('단일 발언의 입력·출력 한도를 확인하세요')
            except ev.ModelResponseError as caught:
                if saved['version'] in (9,10) and len(group)>1 and (saved['version']!=10 or job.request_budget>0):
                    try:
                        planned=policy.plan(rows[cursor:],state['active'],job.tokenizer,limit=max(1,len(group)//2));group=planned['rows'];plan_error=None
                    except model.SplitRequired as error:group=rows[cursor:cursor+1];plan_error=error
                    continue
                error=caught
            error_log.record('context-dialogue-partial',error,path=job.path)
            close(state,group[0]);state['items'].append(failed(source,group,error));state['consecutive_failures']+=1
            break
        check_cancel(job.stop)
        if any(r.get('failed') for r in state['items']) and not (folder/'retry-from.json').exists():save_json(folder/'retry-from.json',before)
        state['cursor']+=len(group);state['batches']+=1
        publish(folder,state)
        job.update(progress={'stage':'dialogue','done':state['cursor'],'total':len(rows),'processed_ms':group[-1]['end_ms'],'duration_ms':source['duration_ms'],'seconds':0})
    if state['phase']=='dialogue':
        close(state);gaps(source,state);state['phase']='chat';publish(folder,state)
    if policy and hasattr(policy,'finalize'):
        state['phase']='grounding';publish(folder,state)
        policy.finalize(job,folder,source,state)
    state['phase']='chat';publish(folder,state)
    if policy and hasattr(policy,'chat'):policy.chat(job,folder,source,state)
    else:chat(job,folder,source,state,policy)
    check_cancel(job.stop)
    state['phase']='done';publish(folder,state)
    failures=sum(bool(r.get('failed') or r.get('chat_state')=='failed') for r in state['items'])
    if saved['version'] in (9,10) and failures and not (folder/'retry-from.json').exists():
        save_json(folder/'retry-from.json',state)
    saved.update(complete=not failures,updated_at=stamp(),tokenizer_seconds=round(job.tokenizer.seconds,3))
    reviews=sum(bool(r.get('evidence_review')) for r in state['items']) if policy else 0
    if policy:saved.update(evidence_reviews=reviews,quality_state='review' if failures or reviews else 'format_checked')
    save_json(folder/'result.json',saved)
    return failures+reviews


def result(folder, saved):
    file=folder/'dialogue-state.json'
    state=read_json(file) if file.exists() else {'items':[],'cursor':0,'active':None,'phase':'dialogue'}
    items=state['items'];active=state['active']
    total=saved.get('speech_units',saved.get('speech_used',0))
    mapping=folder/'utterances.json'
    used=len({r['source_id'] for r in read_json(mapping)['rows'][:state['cursor']]}) if mapping.exists() else 0
    stats={'speech_total':saved.get('speech_total',0),'speech_used':used,
           'chat_total':saved.get('chat_total',0),'chat_used':(sum(r['input']['stats'].get('chat_used',0) for r in items) if saved['version']!=10 else
               len({at['id'] for x in items for r in x['input']['evidence'] if r['kind']=='chat' for at in r.get('occurrences',[{'id':r['id']}])}))}
    ranges=folder/'reaction-ranges.json'
    return {**saved,'items':items,'pending_topic':active,'done':state['cursor'],'total':total,'phase':state['phase'],'stats':stats,
            'reaction_analysis':read_json(ranges) if ranges.exists() else None,
            'item_failures':sum(bool(r.get('failed')) for r in items),'chat_failures':sum(r.get('chat_state')=='failed' for r in items),'boundary_failures':0,
            'evidence_reviews':sum(bool(r.get('evidence_review')) for r in items)}
